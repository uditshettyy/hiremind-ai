"""
app/agents/evaluation/service.py
Owner: Person A (Module 3)

Thin orchestration layer between the router and the pure scoring/report
logic. Handles persistence to `answer_evaluations` / `final_reports`
(ARCHITECTURE.md §3.1).

ASSUMPTION FLAG: this file assumes `app.core.database` exposes an async
`AsyncSession` dependency and `app.core.models` exposes SQLAlchemy ORM
classes named `AnswerEvaluationORM` / `FinalReportORM` mirroring the
`answer_evaluations` / `final_reports` tables from ARCHITECTURE.md §3.1.
Swap these two imports for whatever your Phase-1 `app/core/models.py`
actually calls them — the rest of this file doesn't otherwise touch the DB
layer, so it's a one-line change per model.
"""
from __future__ import annotations

from app.agents.evaluation.report_writer import generate_final_report
from app.agents.evaluation.scorer import evaluate_answer
from app.core.schemas import AnswerEvaluation, FinalReport, InterviewTurn, SkillGapReport

try:  # pragma: no cover - exercised only when the real DB layer is wired up
    from app.core.database import AsyncSession  # type: ignore
    from app.core.models import AnswerEvaluationORM, FinalReportORM  # type: ignore
except ImportError:  # keeps this module importable/testable before app.core.models exists
    AsyncSession = None  # type: ignore
    AnswerEvaluationORM = None  # type: ignore
    FinalReportORM = None  # type: ignore


async def evaluate_and_persist(
    *,
    db,  # AsyncSession, injected via FastAPI Depends in the router
    turn: InterviewTurn,
    skill_gap_report: SkillGapReport,
    session_id: str,
    session_history: list[InterviewTurn],
    job_description_text: str,
    candidate_resume_text: str,
    model: str = "gpt-4o",
    temperature: float = 0.2,
    timeout_seconds: int = 30,
    _generate_structured=None,
) -> AnswerEvaluation:
    """Score an answer, persist the result, and return it.

    Note: `evaluate_answer()` itself has no `db` or `session_id` parameter —
    that's the exact cross-module contract Person B's Interview Agent calls
    directly (ARCHITECTURE.md §5.1). This service function is the *router's*
    entry point, which additionally persists to Postgres; it is not what
    Person B calls.
    """
    kwargs = {
        "turn": turn,
        "skill_gap_report": skill_gap_report,
        "session_history": session_history,
        "job_description_text": job_description_text,
        "candidate_resume_text": candidate_resume_text,
        "model": model,
        "temperature": temperature,
        "timeout_seconds": timeout_seconds,
    }
    if _generate_structured is not None:
        kwargs["_generate_structured"] = _generate_structured

    evaluation = await evaluate_answer(**kwargs)
    # AnswerEvaluation.session_id comes back as "unknown-session" from the pure
    # scorer (see scorer.py's _infer_session_id note) — the service layer knows
    # the real session_id from its own request context, so patch it here.
    evaluation = evaluation.model_copy(update={"session_id": session_id})

    if db is not None and AnswerEvaluationORM is not None:
        row = AnswerEvaluationORM(
            turn_id=None,  # caller should set this from the persisted InterviewTurn row's id
            session_id=session_id,
            dimension_scores=[d.model_dump(mode="json") for d in evaluation.dimension_scores],
            overall_score=evaluation.overall_score,
            weighted_score=evaluation.weighted_score,
            summary_feedback=evaluation.summary_feedback,
            strengths=evaluation.strengths,
            improvements=evaluation.improvements,
            routing_hint=evaluation.routing_hint,
            suggested_follow_up=evaluation.suggested_follow_up,
            skill_level_inferred=(
                evaluation.skill_level_inferred.value if evaluation.skill_level_inferred else None
            ),
            evaluator_version=evaluation.evaluator_version,
            latency_ms=evaluation.latency_ms,
        )
        db.add(row)
        await db.commit()

    return evaluation


async def generate_and_persist_report(
    *,
    db,
    session_id: str,
    candidate_id: str,
    job_id: str,
    turns: list[InterviewTurn],
    skill_gap_report: SkillGapReport,
    total_session_duration_seconds: int,
    _generate_structured=None,
) -> FinalReport:
    kwargs = {
        "session_id": session_id,
        "candidate_id": candidate_id,
        "job_id": job_id,
        "turns": turns,
        "skill_gap_report": skill_gap_report,
        "total_session_duration_seconds": total_session_duration_seconds,
    }
    if _generate_structured is not None:
        kwargs["_generate_structured"] = _generate_structured

    report = await generate_final_report(**kwargs)

    if db is not None and FinalReportORM is not None:
        row = FinalReportORM(
            session_id=session_id,
            overall_score=report.overall_score,
            readiness_level=report.readiness_level,
            dimension_averages={k.value: v for k, v in report.dimension_averages.items()},
            skill_progressions=[p.model_dump(mode="json") for p in report.skill_progressions],
            executive_summary=report.executive_summary,
            top_strengths=report.top_strengths,
            priority_gaps=report.priority_gaps,
            study_plan=report.study_plan,
            total_session_duration_seconds=report.total_session_duration_seconds,
        )
        db.add(row)
        await db.commit()

    return report

