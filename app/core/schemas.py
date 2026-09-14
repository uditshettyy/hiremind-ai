"""
Shared Pydantic models. Single source of truth per ARCHITECTURE.md §2 / §8.1:
"No module redefines them." Only models that cross the Module 1 -> Module 2
(-> Module 3) boundary belong here — intake-internal models like
ResumeProfile / ParsedJobDescription stay local to app/agents/intake/.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ProficiencyLevel(str, Enum):
    """Canonical skill proficiency scale used across the system."""
    EXPERT = "expert"           # 5 — Can teach it
    PROFICIENT = "proficient"   # 4 — Can do it independently
    COMPETENT = "competent"     # 3 — Can do it with some help
    NOVICE = "novice"           # 2 — Basic exposure
    ABSENT = "absent"           # 1 — Not mentioned / no evidence


# Ordinal weight for severity/score math — not in ARCHITECTURE.md's listing,
# but it's a property of the scale itself, so it lives next to the enum.
PROFICIENCY_ORDINAL = {
    ProficiencyLevel.ABSENT: 1,
    ProficiencyLevel.NOVICE: 2,
    ProficiencyLevel.COMPETENT: 3,
    ProficiencyLevel.PROFICIENT: 4,
    ProficiencyLevel.EXPERT: 5,
}


class SkillGap(BaseModel):
    """A single skill gap identified between resume and JD."""
    skill_name: str = Field(..., description="Canonical skill name (normalized)")
    category: str = Field(..., description="e.g., 'technical', 'soft', 'domain', 'tool'")
    jd_required_level: ProficiencyLevel
    resume_claimed_level: ProficiencyLevel
    gap_level: ProficiencyLevel = Field(
        ..., description="The delta: what the candidate needs to reach"
    )
    gap_severity: int = Field(
        ..., ge=1, le=5,
        description="1=minor, 5=critical (computed from level delta + JD priority)",
    )
    jd_evidence: str = Field(..., description="Quoted evidence from the JD")
    resume_evidence: Optional[str] = Field(
        None, description="Quoted evidence from resume, or null if absent"
    )
    suggested_focus: str = Field(
        ..., description="1-sentence coaching hint for the candidate"
    )


class SkillGapReport(BaseModel):
    """The complete skill-gap analysis delivered to the Interview Agent.

    This is **Handoff #1**. Person B's question generator consumes this directly.
    """
    report_id: str = Field(..., description="UUIDv4")
    candidate_id: str
    job_id: str
    generated_at: datetime
    overall_match_score: float = Field(..., ge=0.0, le=1.0)
    top_gaps: List[SkillGap] = Field(
        ..., max_length=10,
        description="Ordered by gap_severity desc. Interview Agent targets these first.",
    )
    strengths: List[SkillGap] = Field(
        ..., description="Skills where resume >= JD requirement (positive reinforcement)"
    )
    metadata: dict = Field(default_factory=dict, description="Extensibility hook")

    @property
    def primary_gap_skills(self) -> List[str]:
        return [g.skill_name for g in self.top_gaps[:5]]