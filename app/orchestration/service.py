"""Phase 6 orchestration service.

Connects the existing Intake, Interview, and Evaluation agents into one
session flow. Agent internals are intentionally left unchanged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.evaluation.service import generate_and_persist_report
from app.agents.intake.jd_parser import ParsedJobDescription
from app.agents.intake.service import (
    analyze_skill_gap,
    parse_jd,
    parse_resume,
)
from app.agents.interview.question_gen import build_question_set_from_gaps
from app.agents.interview.service import (
    create_interview_session,
    get_interview_session,
)
from app.core.models import (
    InterviewSession as InterviewSessionORM,
    SkillGapReportORM,
)
from app.core.schemas import (
    FinalReport,
    InterviewSession,
    InterviewTurn,
    SkillGapReport,
)
from app.utils.llm_client import generate_structured
from app.utils.vector_store import embed_texts


async def start_session(
    *,
    db: AsyncSession,
    resume_filename: str,
    resume_content: bytes,
    job_description_text: str,
    candidate_id: str | None = None,
    job_id: str | None = None,
    candidate_name: str | None = None,
    candidate_email: str | None = None,
) -> tuple[InterviewSession, SkillGapReport, str]:
    """Run Intake -> Skill Gap -> Question Generation -> Interview Session."""

    candidate_id = candidate_id or str(uuid.uuid4())
    job_id = job_id or str(uuid.uuid4())

    # ---------------------------------------------------------
    # 1. Intake: parse resume.
    # ---------------------------------------------------------
    resume_text, _profile = await parse_resume(
        resume_filename,
        resume_content,
        generate_structured,
    )

    # ---------------------------------------------------------
    # 2. Intake: parse job description.
    # ---------------------------------------------------------
    parsed_jd: ParsedJobDescription = await parse_jd(
        job_description_text,
        generate_structured,
    )

    # ---------------------------------------------------------
    # 3. Intake: generate and persist SkillGapReport.
    # ---------------------------------------------------------
    skill_gap_report = await analyze_skill_gap(
        candidate_id=candidate_id,
        job_id=job_id,
        resume_text=resume_text,
        parsed_jd=parsed_jd,
        generate_structured=generate_structured,
        db_session=db,
        embed_fn=embed_texts,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
    )

    # ---------------------------------------------------------
    # 4. Interview Agent: generate QuestionSet.
    # ---------------------------------------------------------
    from openai import AsyncOpenAI
    import os

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured.")

    openai_client = AsyncOpenAI(api_key=api_key)

    question_set = await build_question_set_from_gaps(
        db=db,
        openai_client=openai_client,
        gap_report=skill_gap_report,
    )

    # ---------------------------------------------------------
    # 5. Interview Agent: create persisted InterviewSession.
    # ---------------------------------------------------------
    session = await create_interview_session(
        db=db,
        candidate_id=skill_gap_report.candidate_id,
        job_id=skill_gap_report.job_id,
        skill_gap_report_id=skill_gap_report.report_id,
        question_set=question_set,
    )

    # ---------------------------------------------------------
    # 6. Store the evaluation context in existing config JSON.
    #
    # This avoids modifying InterviewSession's schema/table while
    # making the resume/JD available to the existing WebSocket.
    # ---------------------------------------------------------
    session_uuid = uuid.UUID(session.session_id)

    result = await db.execute(
        select(InterviewSessionORM).where(
            InterviewSessionORM.id == session_uuid
        )
    )

    session_orm = result.scalar_one()

    session_orm.config = {
        **(session_orm.config or {}),
        "resume_text": resume_text,
        "job_description_text": parsed_jd.raw_text,
    }

    await db.commit()
    await db.refresh(session_orm)

    session = session.model_copy(
        update={
            "config": session_orm.config,
            "question_set": question_set,
        }
    )

    return session, skill_gap_report, resume_text


async def finalize_session(
    *,
    db: AsyncSession,
    session_id: str,
) -> FinalReport:
    """Generate and persist the final report for a completed session."""

    # ---------------------------------------------------------
    # 1. Load interview session.
    # ---------------------------------------------------------
    session = await get_interview_session(
        db,
        session_id=session_id,
    )

    if session is None:
        raise ValueError(
            f"Interview session {session_id} was not found."
        )

    # ---------------------------------------------------------
    # 2. Load SkillGapReport.
    # ---------------------------------------------------------
    if session.skill_gap_report_id is None:
        raise ValueError(
            "Interview session does not have a SkillGapReport."
        )

    result = await db.execute(
        select(SkillGapReportORM).where(
            SkillGapReportORM.id == session.skill_gap_report_id
        )
    )

    report_orm = result.scalar_one_or_none()

    if report_orm is None:
        raise ValueError(
            f"SkillGapReport {session.skill_gap_report_id} was not found."
        )

    skill_gap_report = SkillGapReport(
        report_id=str(report_orm.id),
        candidate_id=str(report_orm.candidate_id),
        job_id=str(report_orm.job_id),
        generated_at=report_orm.generated_at,
        overall_match_score=report_orm.overall_match_score,
        top_gaps=report_orm.top_gaps,
        strengths=report_orm.strengths,
        metadata=report_orm.metadata_,
    )

    # ---------------------------------------------------------
    # 3. Load persisted interview turns.
    # ---------------------------------------------------------
    from app.core.models import InterviewTurn as InterviewTurnORM

    turn_result = await db.execute(
        select(InterviewTurnORM)
        .where(InterviewTurnORM.session_id == uuid.UUID(session_id))
        .order_by(InterviewTurnORM.turn_number)
    )

    turn_rows = turn_result.scalars().all()

    turns: list[InterviewTurn] = []

    for row in turn_rows:
        turns.append(
            InterviewTurn(
                turn_number=row.turn_number,
                question=row.question,
                answer_text=row.answer_text,
                answer_started_at=row.answer_started_at,
                answer_submitted_at=row.answer_submitted_at,
                status=row.status,
                evaluation=row.evaluation,
            )
        )

    if not turns:
        raise ValueError(
            "Cannot generate final report because the interview has no turns."
        )

    # ---------------------------------------------------------
    # 4. Calculate session duration.
    # ---------------------------------------------------------
    result = await db.execute(
        select(InterviewSessionORM).where(
            InterviewSessionORM.id == uuid.UUID(session_id)
        )
    )

    session_orm = result.scalar_one()

    started_at = session_orm.started_at
    ended_at = session_orm.ended_at or datetime.now(timezone.utc)

    duration = int(
        max(
            0,
            (ended_at - started_at).total_seconds(),
        )
    )

    # ---------------------------------------------------------
    # 5. Evaluation Agent: generate FinalReport.
    # ---------------------------------------------------------
    return await generate_and_persist_report(
        db=db,
        session_id=session_id,
        candidate_id=session.candidate_id,
        job_id=session.job_id,
        turns=turns,
        skill_gap_report=skill_gap_report,
        total_session_duration_seconds=duration,
        _generate_structured=generate_structured,
    )
