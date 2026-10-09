"""
app/agents/evaluation/scorer.py
Owner: Person A (Module 3)
Caller: Person B (Module 2, inside LangGraph's `evaluation_node`)

This is Handoff #2/#3 from ARCHITECTURE.md §5.1 — the signature below must
not change without a PR tagging Person B (see §5.3 versioning rules).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone

from app.core.exceptions import EvaluationError
from app.core.schemas import (
    DIFFICULTY_WEIGHT,
    AnswerEvaluation,
    DimensionScore,
    InterviewTurn,
    ProficiencyLevel,
    ScoreDimension,
    SkillGapReport,
)
from app.agents.evaluation.prompts import SCORER_SYSTEM_PROMPT, build_scorer_user_prompt
from app.utils.llm_client import (
    GenerateStructured,
    StructuredLLMError,
    generate_structured as default_generate_structured,
)

MIN_ANSWER_WORDS = 8
VALID_ROUTING_HINTS = {"next_question", "follow_up", "drill_deeper", "skip_to_harder"}



async def evaluate_answer(
    *,
    turn: InterviewTurn,
    skill_gap_report: SkillGapReport,
    session_history: list[InterviewTurn],
    job_description_text: str,
    candidate_resume_text: str,
    model: str | None = None,
    temperature: float = 0.2,
    timeout_seconds: int = 30,
    _generate_structured: GenerateStructured = default_generate_structured,
) -> AnswerEvaluation:

    """Evaluate a single answer within the full interview context.

    This function is called **synchronously within the LangGraph loop**
    (i.e., it is awaited by the Interview Agent's evaluation node).
    It must return within `timeout_seconds` or the Interview Agent will
    raise a timeout and degrade gracefully (retry or skip evaluation).

    Args:
        turn: The current turn containing the question + candidate answer.
            `turn.answer_text` must be non-null and non-empty.
        skill_gap_report: The original gap report for this session.
            Used to weight scoring by gap severity.
        session_history: All *previous* evaluated turns (excluding current).
            Used to detect contradictions, measure growth, and avoid
            repetitive feedback.
        job_description_text: Raw JD text (for grounding evaluation).
        candidate_resume_text: Raw resume text (for grounding evaluation).
        model: LLM model identifier passed to the unified LLM client.
        temperature: Sampling temperature for the evaluator LLM.
        timeout_seconds: Hard deadline. Person B's LangGraph node wraps this
            in `asyncio.wait_for` as well — this function also enforces it
            internally so a hung call never blocks the caller silently.
        _generate_structured: Injection point for the LLM call, used by tests
            to avoid hitting a real API. Not part of the public contract
            Person B calls against (they always use the default).

    Returns:
        AnswerEvaluation: Fully populated Pydantic model.

    Raises:
        EvaluationError: If the LLM returns unparseable output or if the
            answer is too short to evaluate meaningfully. The Interview
            Agent catches this and may ask the candidate to elaborate.
    """
    start = time.monotonic()

    if not turn.answer_text or not turn.answer_text.strip():
        raise EvaluationError(
            f"Turn {turn.turn_number} has no answer_text to evaluate.",
            reason="answer_too_short",
        )
    if len(turn.answer_text.split()) < MIN_ANSWER_WORDS:
        raise EvaluationError(
            f"Turn {turn.turn_number} answer is too short ({len(turn.answer_text.split())} "
            f"words) to evaluate meaningfully.",
            reason="answer_too_short",
        )

    skill_gap = skill_gap_report.find_skill(turn.question.target_skill)
    user_prompt = build_scorer_user_prompt(
        turn=turn,
        skill_gap=skill_gap,
        skill_gap_report=skill_gap_report,
        session_history=session_history,
        job_description_text=job_description_text,
        candidate_resume_text=candidate_resume_text,
    )

    try:
        raw = await asyncio.wait_for(
            _generate_structured(
                system_prompt=SCORER_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=model,
                temperature=temperature,
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError as exc:
        raise EvaluationError(
            f"evaluate_answer() exceeded {timeout_seconds}s for turn {turn.turn_number}.",
            reason="timeout",
        ) from exc
    except StructuredLLMError as exc:
        raise EvaluationError(str(exc), reason="unparseable_output") from exc

    try:
        dimension_scores = [
            DimensionScore(
                dimension=ScoreDimension(d["dimension"]),
                score=float(d["score"]),
                rationale=d["rationale"],
            )
            for d in raw["dimension_scores"]
        ]
        summary_feedback = raw["summary_feedback"]
        strengths = raw.get("strengths", [])[:5]
        improvements = raw.get("improvements", [])[:5]
        model_answer_snippet = raw.get("model_answer_snippet")
        skill_level_inferred = (
            ProficiencyLevel(raw["skill_level_inferred"])
            if raw.get("skill_level_inferred")
            else None
        )
        suggested_follow_up = raw.get("suggested_follow_up") or None
    except (KeyError, ValueError, TypeError) as exc:
        raise EvaluationError(
            f"LLM response for turn {turn.turn_number} did not match the expected "
            f"scoring shape: {exc}",
            reason="unparseable_output",
        ) from exc

    if len(dimension_scores) != len(ScoreDimension):
        raise EvaluationError(
            f"Expected {len(ScoreDimension)} dimension scores, got {len(dimension_scores)}.",
            reason="unparseable_output",
        )

    overall_score = sum(d.score for d in dimension_scores) / len(dimension_scores)
    weighted_score = _compute_weighted_score(
        overall_score=overall_score,
        turn=turn,
        skill_gap=skill_gap,
    )
    routing_hint = _decide_routing_hint(
        weighted_score=weighted_score,
        turn=turn,
        session_history=session_history,
        suggested_follow_up=suggested_follow_up,
    )

    latency_ms = int((time.monotonic() - start) * 1000)

    return AnswerEvaluation(
        evaluation_id=str(uuid.uuid4()),
        session_id=_infer_session_id(turn, session_history),
        turn_number=turn.turn_number,
        candidate_id=skill_gap_report.candidate_id,
        evaluated_at=datetime.now(timezone.utc),
        dimension_scores=dimension_scores,
        overall_score=round(overall_score, 2),
        weighted_score=round(weighted_score, 2),
        summary_feedback=summary_feedback,
        strengths=strengths,
        improvements=improvements,
        model_answer_snippet=model_answer_snippet,
        routing_hint=routing_hint,
        suggested_follow_up=suggested_follow_up,
        skill_level_inferred=skill_level_inferred,
        latency_ms=latency_ms,
    )


def _compute_weighted_score(*, overall_score: float, turn: InterviewTurn, skill_gap) -> float:
    """weighted_score = overall_score adjusted by question difficulty + gap severity.

    Harder questions and questions targeting more severe gaps are weighted up
    slightly — a strong answer there is more diagnostic than the same score
    on an easy, low-stakes question.
    """
    difficulty_weight = DIFFICULTY_WEIGHT.get(turn.question.difficulty, 1.0)
    severity_weight = 1.0 + ((skill_gap.gap_severity - 3) * 0.03 if skill_gap else 0.0)
    weighted = overall_score * difficulty_weight * severity_weight
    return max(0.0, min(10.0, weighted))


def _decide_routing_hint(
    *,
    weighted_score: float,
    turn: InterviewTurn,
    session_history: list[InterviewTurn],
    suggested_follow_up: str | None,
) -> str:
    """Provide the Interview Agent's LangGraph conditional edge with a routing
    instruction (ARCHITECTURE.md §6). Person B implements the edge behavior;
    this function only decides which hint applies."""
    already_followed_up = bool(turn.follow_up_turns)

    if weighted_score < 4.0:
        return "drill_deeper" if not already_followed_up else "next_question"
    if 4.0 <= weighted_score < 6.5 and suggested_follow_up and not already_followed_up:
        return "follow_up"
    if weighted_score >= 8.5:
        return "skip_to_harder"
    return "next_question"


def _infer_session_id(turn: InterviewTurn, session_history: list[InterviewTurn]) -> str:
    """session_id isn't on InterviewTurn itself — callers (the router/service
    layer) should prefer passing it explicitly via context. As a fallback for
    direct evaluate_answer() calls, this synthesizes a stable placeholder."""
    return "unknown-session"

