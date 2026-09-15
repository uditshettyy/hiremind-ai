"""Job-description parsing.

The LLM call is kept behind a small callable supplied by the service layer.
No app.utils dependency is required during Phase 1 (the callable is injected).
"""

from pydantic import BaseModel, Field

from app.core.schemas import ProficiencyLevel


class JDRequirement(BaseModel):
    """One structured requirement extracted from a job description."""

    skill_name: str
    category: str
    required_level: ProficiencyLevel
    priority: int = Field(default=3, ge=1, le=5)
    evidence: str


class ParsedJobDescription(BaseModel):
    """Structured job-description representation. Intake-internal (not shared)."""

    title: str | None = None
    company: str | None = None
    requirements: list[JDRequirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    raw_text: str


async def parse_job_description(
    raw_text: str,
    generate_structured=None,
) -> ParsedJobDescription:
    """Parse a raw JD using the supplied structured-LLM callable."""
    if not raw_text.strip():
        raise ValueError("Job description text cannot be empty.")

    if generate_structured is None:
        raise RuntimeError(
            "No LLM callable supplied. Connect the project's shared LLM client "
            "when app/utils/llm_client.py is created."
        )

    from app.agents.intake.prompts import JD_EXTRACTION_SYSTEM

    result = await generate_structured(
        system_prompt=JD_EXTRACTION_SYSTEM,
        user_prompt=f"JOB DESCRIPTION:\n{raw_text}",
        response_model=ParsedJobDescription,
    )

    parsed = (
        result
        if isinstance(result, ParsedJobDescription)
        else ParsedJobDescription.model_validate(result)
    )
    parsed.raw_text = raw_text
    return parsed