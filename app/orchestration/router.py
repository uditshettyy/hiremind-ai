"""Phase 6 orchestration routes."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.schemas import FinalReport, InterviewSession, SkillGapReport
from app.orchestration.service import start_session, finalize_session


router = APIRouter(
    prefix="/session",
    tags=["session-orchestration"],
)


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
