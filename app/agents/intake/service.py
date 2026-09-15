"""Orchestration layer for Module 1: parse -> chunk/embed -> gap analysis.

Per ARCHITECTURE.md's folder structure, service.py is business-logic
*orchestration* — the actual parsing lives in parser.py/jd_parser.py and the
actual comparison logic lives in gap_analyzer.py. This file wires them
together and (new) performs the chunk+embed step into document_chunks that
Module 2's RAG question generator will read from later.

Shared models (ProficiencyLevel, SkillGap, SkillGapReport) are imported from
app/core/schemas.py, never redefined here, per the single-source-of-truth rule.
"""
from typing import Awaitable, Callable, Optional

from app.core.schemas import SkillGapReport  # re-exported for router convenience

from app.agents.intake import gap_analyzer, parser
from app.agents.intake.jd_parser import ParsedJobDescription, parse_job_description
from app.agents.intake.parser import ResumeProfile, parse_resume as _parse_resume


async def parse_resume(
    filename: str,
    content: bytes,
    generate_structured: Callable[..., Awaitable] | None = None,
) -> tuple[str, ResumeProfile]:
    """Thin pass-through — kept here so router.py has one import surface."""
    return await _parse_resume(filename, content, generate_structured)


async def parse_jd(
    raw_text: str,
    generate_structured: Callable[..., Awaitable] | None = None,
) -> ParsedJobDescription:
    """Thin pass-through — kept here so router.py has one import surface."""
    return await parse_job_description(raw_text, generate_structured)


import logging
import uuid

logger = logging.getLogger(__name__)


async def _chunk_and_embed(
    *,
    source_type: str,
    source_id: str,
    text: str,
    db_session,
    embed_fn: Callable[..., Awaitable] | None,
) -> None:
    """Write resume/JD text into document_chunks for Module 2's RAG retrieval.

    No-op when db_session/embed_fn aren't supplied, so Phase-1 tests (and any
    caller not yet wired to Postgres/an embedding model) keep working without
    a real database. Wire real values in once app/utils/vector_store.py and
    the DB session dependency exist.
    """
    if db_session is None or embed_fn is None:
        return

    try:
        from app.core.models import DocumentChunk  # SQLAlchemy ORM model, §3.1

        try:
            parsed_uuid = uuid.UUID(source_id)
        except (ValueError, TypeError, AttributeError):
            parsed_uuid = uuid.uuid5(uuid.NAMESPACE_URL, f"{source_type}:{source_id}")

        chunk_size, overlap = 800, 100
        chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size - overlap)]
        if not chunks:
            return

        vectors = await embed_fn(chunks)
        for piece, vector in zip(chunks, vectors):
            db_session.add(
                DocumentChunk(source_type=source_type, source_id=parsed_uuid, chunk_text=piece, embedding=vector)
            )
        await db_session.flush()
    except Exception as exc:
        logger.warning("Failed to chunk and embed document (source_type=%s, source_id=%s): %s", source_type, source_id, exc)


async def analyze_skill_gap(
    *,
    candidate_id: str,
    job_id: str,
    resume_text: str,
    parsed_jd: ParsedJobDescription,
    generate_structured: Callable[..., Awaitable] | None = None,
    db_session=None,
    embed_fn: Callable[..., Awaitable] | None = None,
) -> SkillGapReport:
    """parse (already done by caller) -> chunk/embed -> gap analysis."""
    await _chunk_and_embed(
        source_type="resume", source_id=candidate_id, text=resume_text,
        db_session=db_session, embed_fn=embed_fn,
    )
    await _chunk_and_embed(
        source_type="jd", source_id=job_id, text=parsed_jd.raw_text,
        db_session=db_session, embed_fn=embed_fn,
    )
    return await gap_analyzer.build_skill_gap_report(
        candidate_id=candidate_id,
        job_id=job_id,
        resume_text=resume_text,
        parsed_jd=parsed_jd,
        generate_structured=generate_structured,
    )