"""Skill-gap analysis: the LLM prompt + gap scoring logic for Module 1.

Per ARCHITECTURE.md's folder structure, this file (not service.py) owns the
comparison logic. service.py should only orchestrate (parse -> chunk/embed ->
call this).
"""
from datetime import datetime, timezone
from typing import Callable, Awaitable
from uuid import uuid4

from pydantic import BaseModel, Field

from app.core.schemas import SkillGap, SkillGapReport
from app.agents.intake.jd_parser import ParsedJobDescription
from app.agents.intake.prompts import GAP_ANALYSIS_SYSTEM


class RawSkillGapAnalysis(BaseModel):
    """What we ask the LLM for directly.

    Deliberately does NOT carry SkillGapReport's `max_length=10` constraint
    on top_gaps: the LLM may legitimately surface more than 10 real gaps for
    a given resume/JD pair, and we want our own sort-then-slice logic below
    to decide which 10 make the cut — not have the whole request hard-fail
    validation because the candidate happened to be a bad fit. Identity/
    timestamp fields (report_id, candidate_id, job_id, generated_at) are
    intentionally excluded here too — build_skill_gap_report sets those
    itself rather than trusting the LLM's output for them.
    """
    overall_match_score: float = Field(..., ge=0.0, le=1.0)
    top_gaps: list[SkillGap] = Field(default_factory=list)
    strengths: list[SkillGap] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


async def build_skill_gap_report(
    *,
    candidate_id: str,
    job_id: str,
    resume_text: str,
    parsed_jd: ParsedJobDescription,
    generate_structured: Callable[..., Awaitable] | None = None,
) -> SkillGapReport:
    """Use the LLM to semantically compare resume evidence with JD requirements."""
    if generate_structured is None:
        raise RuntimeError(
            "No LLM callable supplied. Connect the project's shared LLM client "
            "when app/utils/llm_client.py is created."
        )

    user_prompt = f"""CANDIDATE ID: {candidate_id}
JOB ID: {job_id}

RESUME:
{resume_text}

STRUCTURED JD:
{parsed_jd.model_dump_json(indent=2)}
"""

    result = await generate_structured(
        system_prompt=GAP_ANALYSIS_SYSTEM,
        user_prompt=user_prompt,
        response_model=RawSkillGapAnalysis,
    )

    raw = (
        result
        if isinstance(result, RawSkillGapAnalysis)
        else RawSkillGapAnalysis.model_validate(result)
    )

    top_gaps = sorted(raw.top_gaps, key=lambda gap: gap.gap_severity, reverse=True)[:10]

    return SkillGapReport(
        report_id=str(uuid4()),
        candidate_id=candidate_id,
        job_id=job_id,
        generated_at=datetime.now(timezone.utc),
        overall_match_score=raw.overall_match_score,
        top_gaps=top_gaps,
        strengths=raw.strengths,
        metadata=raw.metadata,
    )