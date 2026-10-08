"""FastAPI routes for Module 1.

generate_structured is resolved via a FastAPI dependency (`get_generate_structured`)
so the LLM client can be swapped/mocked without touching route code. Until
app/utils/llm_client.py exists, the default dependency returns None and routes
respond 503 (not an unhandled 500) so the "not wired yet" state is explicit.
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.utils.llm_client import generate_structured as _generate_structured
from app.utils.vector_store import embed_texts

from .jd_parser import ParsedJobDescription
from .service import analyze_skill_gap, parse_jd, parse_resume


router = APIRouter(prefix="", tags=["intake"])


async def get_generate_structured():
    """Dependency seam for the shared LLM client — now wired to the real one.

    Kept as a dependency (rather than importing generate_structured directly
    in each route) so tests can still override this with a mock via
    app.dependency_overrides, same DI pattern as get_db.
    """
    return _generate_structured


class JDRequest(BaseModel):
    raw_text: str


class SkillGapRequest(BaseModel):
    candidate_id: str
    job_id: str
    resume_text: str
    parsed_jd: ParsedJobDescription
    candidate_name: Optional[str] = None
    candidate_email: Optional[str] = None


from app.utils.llm_client import LLMError, LLMRateLimitError


def _handle_llm_errors(exc: Exception):
    if isinstance(exc, (RuntimeError, LLMRateLimitError)):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, LLMError):
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise exc


@router.post("/parse/resume")
async def parse_resume_route(
    file: UploadFile = File(...),
    generate_structured=Depends(get_generate_structured),
):
    filename = file.filename or ""

    if not filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=415,
            detail="Only PDF and DOCX resumes are supported.",
        )

    try:
        content = await file.read()
        resume_text, profile = await parse_resume(filename, content, generate_structured)
        return {"resume_text": resume_text, "profile": profile}
    except (ValueError, RuntimeError) as exc:
        _handle_llm_errors(exc)


@router.post("/parse/jd")
async def parse_jd_route(
    request: JDRequest,
    generate_structured=Depends(get_generate_structured),
):
    try:
        return await parse_jd(request.raw_text, generate_structured)
    except (ValueError, RuntimeError) as exc:
        _handle_llm_errors(exc)


@router.post("/analyze/skill-gap")
async def analyze_skill_gap_route(
    request: SkillGapRequest,
    generate_structured=Depends(get_generate_structured),
    db: AsyncSession = Depends(get_db),
):
    try:
        # request.parsed_jd is already a validated ParsedJobDescription — the
        # previous version declared this field as a bare `dict`, which broke
        # gap_analyzer's `.model_dump_json()` call at runtime.
        return await analyze_skill_gap(
            candidate_id=request.candidate_id,
            job_id=request.job_id,
            resume_text=request.resume_text,
            parsed_jd=request.parsed_jd,
            generate_structured=generate_structured,
            db_session=db,
            embed_fn=embed_texts,
            candidate_name=request.candidate_name,
            candidate_email=request.candidate_email,
        )
    except (ValueError, RuntimeError) as exc:
        _handle_llm_errors(exc)