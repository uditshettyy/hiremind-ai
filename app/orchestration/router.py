"""Phase 6 orchestration routes."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import (
    FinalReport,
    InterviewSession,
    SessionStatus,
    SkillGapReport,
)
from app.orchestration.service import start_session, finalize_session
from app.agents.interview import session_store
from app.agents.interview.llm_question_gen import generate_questions_from_gaps


router = APIRouter(
    prefix="/session",
    tags=["session-orchestration"],
)


class BootstrapRequest(BaseModel):
    """Lightweight session bootstrap — no DB required.

    Called by the frontend after the three-step parse flow
    (parse/resume → parse/jd → analyze/skill-gap) so the WebSocket
    has a session to load even when Postgres is unavailable.
    """
    skill_gap_report: SkillGapReport
    resume_text: str
    job_description_text: str


@router.post("/bootstrap")
async def bootstrap_session_route(body: BootstrapRequest):
    """Create an in-memory InterviewSession from an already-computed SkillGapReport.

    Returns session_id + websocket_path. The WebSocket handler uses the
    in-memory store when no DB row is found.
    """
    try:
        question_set = await generate_questions_from_gaps(
            skill_gap_report=body.skill_gap_report,
            resume_text=body.resume_text,
            job_description_text=body.job_description_text,
        )

        session_id = str(uuid.uuid4())
        question_set = question_set.model_copy(update={"session_id": session_id})

        session = InterviewSession(
            session_id=session_id,
            candidate_id=body.skill_gap_report.candidate_id,
            job_id=body.skill_gap_report.job_id,
            skill_gap_report_id=body.skill_gap_report.report_id,
            status=SessionStatus.CREATED,
            session_started_at=datetime.now(timezone.utc),
            question_set=question_set,
            current_turn_number=0,
            turns=[],
            config={
                "resume_text": body.resume_text,
                "job_description_text": body.job_description_text,
            },
        )

        session_store.save(
            session=session,
            skill_gap_report=body.skill_gap_report,
            resume_text=body.resume_text,
            job_description_text=body.job_description_text,
        )

        return {
            "session_id": session_id,
            "websocket_path": f"/ws/interview/{session_id}",
            "total_questions": len(question_set.questions),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/start")
async def start_session_route(
    resume: UploadFile = File(...),
    job_description: str = Form(...),
    candidate_id: str | None = Form(None),
    job_id: str | None = Form(None),
    candidate_name: str | None = Form(None),
    candidate_email: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Start the complete Phase 6 session flow."""

    if not resume.filename:
        raise HTTPException(
            status_code=400,
            detail="Resume filename is required.",
        )

    if not resume.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=415,
            detail="Only PDF and DOCX resumes are supported.",
        )

    if not job_description.strip():
        raise HTTPException(
            status_code=400,
            detail="Job description must not be empty.",
        )

    try:
        resume_content = await resume.read()

        session, skill_gap_report, _resume_text = await start_session(
            db=db,
            resume_filename=resume.filename,
            resume_content=resume_content,
            job_description_text=job_description,
            candidate_id=candidate_id,
            job_id=job_id,
            candidate_name=candidate_name,
            candidate_email=candidate_email,
        )

        return {
            "session": session,
            "skill_gap_report": skill_gap_report,
            "websocket_path": f"/ws/interview/{session.session_id}",
        }

    except (ValueError, RuntimeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.post(
    "/{session_id}/finalize",
    response_model=FinalReport,
)
async def finalize_session_route(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Generate the FinalReport after the interview is completed."""
    # ── In-memory path fallback (when Postgres is not used) ──
    mem_entry = session_store.load(session_id)
    if mem_entry is not None:
        session, skill_gap_report, _resume_text, _jd_text = mem_entry
        from app.agents.evaluation.service import generate_and_persist_report
        from app.utils.llm_client import generate_structured

        started_at = session.session_started_at
        ended_at = datetime.now(timezone.utc)
        duration = int(max(0, (ended_at - started_at).total_seconds())) if started_at else 600

        try:
            return await generate_and_persist_report(
                db=None,
                session_id=session_id,
                candidate_id=session.candidate_id,
                job_id=session.job_id,
                turns=session.turns,
                skill_gap_report=skill_gap_report,
                total_session_duration_seconds=duration,
                _generate_structured=generate_structured,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Finalize session failed: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    try:
        return await finalize_session(
            db=db,
            session_id=session_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc
