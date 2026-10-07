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
import uuid

from pydantic import BaseModel, ConfigDict, Field


class ProficiencyLevel(str, Enum):
    """Canonical skill proficiency scale used across the system."""
    EXPERT = "expert"           # 5 — Can teach it
    PROFICIENT = "proficient"   # 4 — Can do it independently
    COMPETENT = "competent"     # 3 — Can do it with some help
    NOVICE = "novice"           # 2 — Basic exposure
    ABSENT = "absent"           # 1 — Not mentioned / no evidence


# Ordinal weight for severity/score math — not in ARCHITECTURE.md's listing,
# but it's a property of the scale itself, so it lives next to the enum.
PROFICIENCY_ORDINAL: dict[ProficiencyLevel, int] = {
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

    def find_skill(self, skill_name: str) -> Optional[SkillGap]:
        """Find a skill gap or strength entry by canonical skill_name (case-insensitive)."""
        norm = skill_name.strip().lower()
        for g in self.top_gaps + self.strengths:
            if g.skill_name.strip().lower() == norm:
                return g
        return None


class QuestionType(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    FOLLOW_UP = "follow_up"      # Generated dynamically during the loop
    CLARIFYING = "clarifying"    # When the model needs more info


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# Used by scorer.py to weight overall_score -> weighted_score by question difficulty
DIFFICULTY_WEIGHT: dict[Difficulty, float] = {
    Difficulty.EASY: 0.85,
    Difficulty.MEDIUM: 1.0,
    Difficulty.HARD: 1.15,
}


class Question(BaseModel):
    """A single interview question with full provenance."""
    question_id: str = Field(..., description="UUIDv4")
    question_text: str
    question_type: QuestionType
    target_skill: str = Field(..., description="Which gap or strength this probes")
    target_skill_gap_id: Optional[str] = Field(
        None, description="FK to SkillGap if derived from gap report"
    )
    difficulty: Difficulty
    expected_bullet_points: List[str] = Field(
        default_factory=list,
        description="Rubric: what a strong answer should cover"
    )
    max_duration_seconds: int = Field(180, description="Recommended answer time limit")
    source_chunks: List[str] = Field(
        default_factory=list,
        description="pgvector chunk IDs used for RAG context (audit trail)"
    )


class QuestionSet(BaseModel):
    """The planned question sequence for a session. May be mutated by LangGraph."""
    set_id: str
    session_id: str
    questions: List[Question]
    created_at: datetime


class QuestionBankItem(BaseModel):
    """A single curated question from the vector store."""
    id: Optional[uuid.UUID] = None
    question_text: str = Field(..., description="The actual interview question")
    category: str = Field(..., description="technical | behavioral | project-deep-dive | dsa")
    question_type: QuestionType = Field(default=QuestionType.TECHNICAL)
    difficulty: Difficulty = Field(default=Difficulty.MEDIUM)
    target_skills: List[str] = Field(default_factory=list, description="Skill tags for filtering")
    expected_bullet_points: List[str] = Field(default_factory=list)
    max_duration_seconds: int = Field(default=180)
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class QuestionBankSearchResult(BaseModel):
    """Wrapper for retrieval results including similarity score."""
    question: QuestionBankItem
    similarity_score: float = Field(..., description="Cosine similarity (0-1, higher is better)")


class QuestionBankBatch(BaseModel):
    """Input shape for the ingestion script."""
    questions: List[QuestionBankItem]


# ---------------------------------------------------------------------------
# Module 2 & 3: Turn and Evaluation Models
# ---------------------------------------------------------------------------

class TurnStatus(str, Enum):
    PENDING = "pending"        # Question asked, awaiting answer
    ANSWERED = "answered"      # Answer received, awaiting evaluation
    EVALUATED = "evaluated"    # Evaluation complete
    FOLLOW_UP = "follow_up"    # A follow-up was asked
    SKIPPED = "skipped"        # Question skipped (time/choice)


class ScoreDimension(str, Enum):
    ACCURACY = "accuracy"        # Factually correct?
    DEPTH = "depth"              # Nuanced understanding?
    CLARITY = "clarity"          # Well-structured communication?
    RELEVANCE = "relevance"      # Addresses the question asked?
    CONFIDENCE = "confidence"    # Tone / delivery (text proxy)


class DimensionScore(BaseModel):
    dimension: ScoreDimension
    score: float = Field(..., ge=0.0, le=10.0)
    rationale: str = Field(..., max_length=500)


class AnswerEvaluation(BaseModel):
    """The atomic evaluation returned by Module 3 for a single answer (Handoff #3)."""
    evaluation_id: str = Field(..., description="UUIDv4")
    session_id: str
    turn_number: int
    candidate_id: str
    evaluated_at: datetime

    dimension_scores: List[DimensionScore]
    overall_score: float = Field(..., ge=0.0, le=10.0)
    weighted_score: float = Field(..., ge=0.0, le=10.0)

    summary_feedback: str = Field(..., max_length=2000)
    strengths: List[str] = Field(default_factory=list, max_length=5)
    improvements: List[str] = Field(default_factory=list, max_length=5)
    model_answer_snippet: Optional[str] = None

    routing_hint: str = Field(
        ..., description="One of: 'next_question', 'follow_up', 'drill_deeper', 'skip_to_harder'"
    )
    suggested_follow_up: Optional[str] = None
    skill_level_inferred: Optional[ProficiencyLevel] = None

    evaluator_version: str = Field(default="1.0.0")
    latency_ms: int = Field(..., description="Evaluation inference time")


class InterviewTurn(BaseModel):
    """A single Q-A-evaluation cycle."""
    turn_number: int
    question: Question
    answer_text: Optional[str] = None
    answer_audio_url: Optional[str] = None
    answer_started_at: Optional[datetime] = None
    answer_submitted_at: Optional[datetime] = None
    status: TurnStatus = TurnStatus.PENDING
    evaluation: Optional[AnswerEvaluation] = None
    follow_up_turns: List[InterviewTurn] = Field(
        default_factory=list,
        description="Nested follow-ups (tree structure, usually depth <= 2)"
    )


class SessionStatus(str, Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class InterviewSession(BaseModel):
    """Top-level LangGraph state object."""
    session_id: str = Field(..., description="UUIDv4")
    candidate_id: str
    job_id: str
    skill_gap_report_id: str
    status: SessionStatus
    current_turn_number: int = 0
    turns: List[InterviewTurn] = Field(default_factory=list)
    question_set: QuestionSet
    session_started_at: datetime
    session_ended_at: Optional[datetime] = None
    config: dict = Field(
        default_factory=lambda: {
            "max_turns": 12,
            "allow_follow_ups": True,
        }
    )

    @property
    def completed_turns(self) -> List[InterviewTurn]:
        return [t for t in self.turns if t.status == TurnStatus.EVALUATED]


class SkillProgression(BaseModel):
    skill_name: str
    initial_gap: ProficiencyLevel
    final_inferred_level: ProficiencyLevel
    progression_delta: int
    evidence_turns: List[int]


class FinalReport(BaseModel):
    report_id: str
    session_id: str
    candidate_id: str
    job_id: str
    generated_at: datetime

    overall_score: float = Field(..., ge=0.0, le=10.0)
    percentile_estimate: Optional[float] = Field(None, ge=0.0, le=100.0)
    readiness_level: str = Field(..., description="e.g., 'ready', 'needs_work', 'not_ready'")

    dimension_averages: dict[ScoreDimension, float]
    skill_progressions: List[SkillProgression]
    per_turn_evaluations: List[AnswerEvaluation]

    executive_summary: str
    top_strengths: List[str]
    priority_gaps: List[str]
    study_plan: List[str] = Field(default_factory=list)

    total_session_duration_seconds: int
    total_turns: int
    report_version: str = "1.0.0"
