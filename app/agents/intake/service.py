"""Orchestration layer for Module 1: parse -> chunk/embed -> gap analysis.

Per ARCHITECTURE.md's folder structure, service.py is business-logic
*orchestration* — the actual parsing lives in parser.py/jd_parser.py and the
actual comparison logic lives in gap_analyzer.py. This file wires them
together and performs chunk+embed step into document_chunks as well as
persisting Candidate, Job, and SkillGapReport records for Module 2 and 3.

Shared models (ProficiencyLevel, SkillGap, SkillGapReport) are imported from
app/core/schemas.py, never redefined here, per the single-source-of-truth rule.
"""
import logging
from typing import Awaitable, Callable, Optional
import uuid

from app.core.schemas import SkillGapReport  # re-exported for router convenience

from app.agents.intake import gap_analyzer, parser
from app.agents.intake.jd_parser import ParsedJobDescription, parse_job_description
from app.agents.intake.parser import ResumeProfile, parse_resume as _parse_resume

logger = logging.getLogger(__name__)


def parse_or_gen_uuid(val: str, namespace: str) -> uuid.UUID:
    """Safely parse a string as UUID v4, or generate a deterministic UUID v5 if non-UUID."""
    try:
        return uuid.UUID(val)
    except (ValueError, TypeError, AttributeError):
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace}:{val}")


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


async def _chunk_and_embed(
    *,
    source_type: str,
    source_id: str,
    text: str,
    db_session,
    embed_fn: Callable[..., Awaitable] | None,
) -> None:
    """Write resume/JD text into document_chunks for Module 2's RAG retrieval."""
    if db_session is None or embed_fn is None:
        return

    try:
        from app.core.models import DocumentChunk  # SQLAlchemy ORM model, §3.1

        parsed_uuid = parse_or_gen_uuid(source_id, source_type)

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
        logger.error("Failed to chunk and embed document (source_type=%s, source_id=%s): %s", source_type, source_id, exc)
        raise RuntimeError(f"Database error during chunk embedding: {exc}") from exc


async def _persist_intake_entities(
    *,
    candidate_id: str,
    job_id: str,
    parsed_jd: ParsedJobDescription,
    report: SkillGapReport,
    db_session,
    candidate_name: Optional[str] = None,
    candidate_email: Optional[str] = None,
) -> None:
    """Persist Candidate, Job, and SkillGapReport records to Postgres."""
    if db_session is None:
        return

    try:
        from app.core.models import Candidate, Job, SkillGapReportORM

        cand_uuid = parse_or_gen_uuid(candidate_id, "candidate")
        job_uuid = parse_or_gen_uuid(job_id, "job")
        report_uuid = parse_or_gen_uuid(report.report_id, "skill_gap_report")

        email = candidate_email or f"candidate_{str(cand_uuid)[:8]}@example.com"
        name = candidate_name or "Candidate"

        # 1. Ensure Candidate record
        existing_cand = await db_session.get(Candidate, cand_uuid)
        if existing_cand is None:
            db_session.add(
                Candidate(
                    id=cand_uuid,
                    email=email,
                    name=name,
                )
            )

        # 2. Ensure Job record
        existing_job = await db_session.get(Job, job_uuid)
        if existing_job is None:
            db_session.add(
                Job(
                    id=job_uuid,
                    title=parsed_jd.title or "Job Description",
                    company=parsed_jd.company,
                    raw_description=parsed_jd.raw_text,
                    parsed_requirements=parsed_jd.model_dump(mode="json"),
                )
            )

        # 3. Ensure SkillGapReportORM record
        existing_report = await db_session.get(SkillGapReportORM, report_uuid)
        if existing_report is None:
            db_session.add(
                SkillGapReportORM(
                    id=report_uuid,
                    candidate_id=cand_uuid,
                    job_id=job_uuid,
                    overall_match_score=report.overall_match_score,
                    top_gaps=[g.model_dump(mode="json") for g in report.top_gaps],
                    strengths=[g.model_dump(mode="json") for g in report.strengths],
                    metadata_=report.metadata,
                )
            )

        await db_session.flush()
    except Exception as exc:
        logger.error("Failed to persist intake entities to DB: %s", exc)
        raise RuntimeError(f"Database error during intake entity persistence: {exc}") from exc


async def analyze_skill_gap(
    *,
    candidate_id: str,
    job_id: str,
    resume_text: str,
    parsed_jd: ParsedJobDescription,
    generate_structured: Callable[..., Awaitable] | None = None,
    db_session=None,
    embed_fn: Callable[..., Awaitable] | None = None,
    candidate_name: Optional[str] = None,
    candidate_email: Optional[str] = None,
) -> SkillGapReport:
    """parse (already done by caller) -> chunk/embed -> gap analysis -> DB persistence."""
    cand_uuid = parse_or_gen_uuid(candidate_id, "candidate")
    job_uuid = parse_or_gen_uuid(job_id, "job")

    await _chunk_and_embed(
        source_type="resume", source_id=str(cand_uuid), text=resume_text,
        db_session=db_session, embed_fn=embed_fn,
    )
    await _chunk_and_embed(
        source_type="jd", source_id=str(job_uuid), text=parsed_jd.raw_text,
        db_session=db_session, embed_fn=embed_fn,
    )

    report = await gap_analyzer.build_skill_gap_report(
        candidate_id=candidate_id,
        job_id=job_id,
        resume_text=resume_text,
        parsed_jd=parsed_jd,
        generate_structured=generate_structured,
    )

    await _persist_intake_entities(
        candidate_id=candidate_id,
        job_id=job_id,
        parsed_jd=parsed_jd,
        report=report,
        db_session=db_session,
        candidate_name=candidate_name,
        candidate_email=candidate_email,
    )

    if db_session is not None and hasattr(db_session, "commit"):
        try:
            await db_session.commit()
        except Exception as exc:
            logger.error("Failed to commit intake DB transaction: %s", exc)
            if hasattr(db_session, "rollback"):
                await db_session.rollback()
            raise RuntimeError(f"Database transaction commit failed: {exc}") from exc

    return report