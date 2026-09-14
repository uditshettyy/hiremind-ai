# app/core/schemas.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid

from enum import Enum

class QuestionType(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    FOLLOW_UP = "follow_up"
    CLARIFYING = "clarifying"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


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

    class Config:
        from_attributes = True  # SQLAlchemy → Pydantic


class QuestionBankSearchResult(BaseModel):
    """Wrapper for retrieval results including similarity score."""
    question: QuestionBankItem
    similarity_score: float = Field(..., description="Cosine similarity (0-1, higher is better)")


class QuestionBankBatch(BaseModel):
    """Input shape for the ingestion script."""
    questions: List[QuestionBankItem]