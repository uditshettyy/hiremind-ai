"""
app/agents/evaluation/report_writer.py
Owner: Person A (Module 3)

Synthesizes a FinalReport from a full transcript of evaluated turns plus the
session's original SkillGapReport. Called at end-of-session (ARCHITECTURE.md
§6, END node) as a background task, and via POST /report/generate.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from app.core.exceptions import ReportGenerationError
from app.core.schemas import (
    PROFICIENCY_ORDINAL,
    AnswerEvaluation,
    FinalReport,
    InterviewTurn,
    ProficiencyLevel,
    ScoreDimension,
    SkillGapReport,
    SkillProgression,
)
from app.agents.evaluation.prompts import REPORT_SYSTEM_PROMPT, build_report_user_prompt
from app.utils.llm_client import (
    GenerateStructured,
    StructuredLLMError,
    generate_structured as default_generate_structured,
)

READINESS_THRESHOLDS = (
    (7.5, "ready"),
    (5.0, "needs_work"),
    (0.0, "not_ready"),
)


async def generate_final_report(
    *,
    session_id: str,
    candidate_id: str,
    job_id: str,
    turns: list[InterviewTurn],
    skill_gap_report: SkillGapReport,
    total_session_duration_seconds: int,
    model: str = "gpt-4o",
    temperature: float = 0.3,
    timeout_seconds: int = 45,
    _generate_structured: GenerateStructured = default_generate_structured,
) -> FinalReport:
    """Build the end-of-session FinalReport (ARCHITECTURE.md §2.5).

    Args:
        session_id, candidate_id, job_id: session identifiers.
        turns: the full turn list for the session. Only turns with
            status == EVALUATED and a populated `evaluation` contribute.
        skill_gap_report: the report that seeded this session — gives each
            skill's initial gap level to compare against what the interview
            revealed.
        total_session_duration_seconds: wall-clock duration of the session.

    Raises:
        ReportGenerationError: if there are no evaluated turns to report on.
    """
    evaluated_turns = [t for t in turns if t.evaluation is not None]
    if not evaluated_turns:
        raise ReportGenerationError(
            f"Session {session_id} has no evaluated turns — cannot generate a report."
        )

    evaluations = [t.evaluation for t in evaluated_turns]  # type: ignore[misc]

    overall_score = round(
        sum(e.weighted_score for e in evaluations) / len(evaluations), 2
    )
    dimension_averages = _compute_dimension_averages(evaluations)
    readiness_level = _readiness_level(overall_score)
    skill_progressions = _compute_skill_progressions(evaluated_turns, skill_gap_report)

    per_turn_summaries = [
        f"- Turn {t.turn_number} ({t.question.target_skill}, {t.question.question_type.value}): "
        f"weighted_score={t.evaluation.weighted_score:.1f}, "
        f"strengths={t.evaluation.strengths}, improvements={t.evaluation.improvements}"
        for t in evaluated_turns
    ]
    progression_summaries = [
        f"- {p.skill_name}: {p.initial_gap.value} -> {p.final_inferred_level.value} "
        f"(delta {p.progression_delta:+d})"
        for p in skill_progressions
    ]

    user_prompt = build_report_user_prompt(
        dimension_averages={k.value: v for k, v in dimension_averages.items()},
        overall_score=overall_score,
        readiness_level=readiness_level,
        per_turn_summaries=per_turn_summaries,
        skill_progression_summaries=progression_summaries,
    )

    try:
        raw = await asyncio.wait_for(
            _generate_structured(
                system_prompt=REPORT_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise ReportGenerationError(
            f"generate_final_report() exceeded {timeout_seconds}s for session {session_id}."
        ) from exc
    except StructuredLLMError as exc:
        raise ReportGenerationError(str(exc)) from exc

    try:
        executive_summary = raw["executive_summary"]
        top_strengths = raw.get("top_strengths", [])[:5]
        priority_gaps = raw.get("priority_gaps", [])[:5]
        study_plan = raw.get("study_plan", [])[:8]
    except KeyError as exc:
        raise ReportGenerationError(
            f"LLM response for session {session_id} report did not match the expected shape: {exc}"
        ) from exc

    return FinalReport(
        report_id=str(uuid.uuid4()),
        session_id=session_id,
        candidate_id=candidate_id,
        job_id=job_id,
        generated_at=datetime.now(timezone.utc),
        overall_score=overall_score,
        percentile_estimate=None,  # requires a population baseline; not available yet
        readiness_level=readiness_level,
        dimension_averages=dimension_averages,
        skill_progressions=skill_progressions,
        per_turn_evaluations=evaluations,
        executive_summary=executive_summary,
        top_strengths=top_strengths,
        priority_gaps=priority_gaps,
        study_plan=study_plan,
        total_session_duration_seconds=total_session_duration_seconds,
        total_turns=len(turns),
    )


def _compute_dimension_averages(
    evaluations: list[AnswerEvaluation],
) -> dict[ScoreDimension, float]:
    sums: dict[ScoreDimension, float] = defaultdict(float)
    counts: dict[ScoreDimension, int] = defaultdict(int)
    for e in evaluations:
        for ds in e.dimension_scores:
            sums[ds.dimension] += ds.score
            counts[ds.dimension] += 1
    return {dim: round(sums[dim] / counts[dim], 2) for dim in sums}


def _readiness_level(overall_score: float) -> str:
    for threshold, label in READINESS_THRESHOLDS:
        if overall_score >= threshold:
            return label
    return "not_ready"


def _compute_skill_progressions(
    evaluated_turns: list[InterviewTurn],
    skill_gap_report: SkillGapReport,
) -> list[SkillProgression]:
    """Group evaluated turns by target skill, compare the report's initial gap
    against the *last* inferred level the interview produced for that skill."""
    by_skill: dict[str, list[InterviewTurn]] = defaultdict(list)
    for t in evaluated_turns:
        by_skill[t.question.target_skill].append(t)

    progressions: list[SkillProgression] = []
    for skill_name, skill_turns in by_skill.items():
        gap_entry = skill_gap_report.find_skill(skill_name)
        initial_gap = gap_entry.resume_claimed_level if gap_entry else ProficiencyLevel.ABSENT

        inferred_levels = [
            t.evaluation.skill_level_inferred
            for t in skill_turns
            if t.evaluation and t.evaluation.skill_level_inferred is not None
        ]
        final_level = inferred_levels[-1] if inferred_levels else initial_gap

        progressions.append(
            SkillProgression(
                skill_name=skill_name,
                initial_gap=initial_gap,
                final_inferred_level=final_level,
                progression_delta=(
                    PROFICIENCY_ORDINAL[final_level] - PROFICIENCY_ORDINAL[initial_gap]
                ),
                evidence_turns=[t.turn_number for t in skill_turns],
            )
        )

    # Order by |delta| desc so the most notable movement (up or down) surfaces first
    progressions.sort(key=lambda p: abs(p.progression_delta), reverse=True)
    return progressions

