"""SQLAlchemy ORM models mirroring ARCHITECTURE.md §3.1.

Single shared file per §8.1 (same rule as core/schemas.py) — don't fork a
second copy of any of these tables elsewhere.
"""
from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base


def _uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(unique=True, nullable=False)
    name: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    title: Mapped[str] = mapped_column(nullable=False)
    company: Mapped[str | None]
    raw_description: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_requirements: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class SkillGapReportORM(Base):
    """ORM row for a persisted SkillGapReport (app.core.schemas.SkillGapReport)."""
    __tablename__ = "skill_gap_reports"
    __table_args__ = (
        CheckConstraint("overall_match_score BETWEEN 0.0 AND 1.0"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    overall_match_score: Mapped[float]
    top_gaps: Mapped[list] = mapped_column(JSONB, default=list)
    strengths: Mapped[list] = mapped_column(JSONB, default=list)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class DocumentChunk(Base):
    """RAG store for resume/JD/knowledge-base text, per §3.1."""
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_type: Mapped[str] = mapped_column(nullable=False)  # 'resume' | 'jd' | 'knowledge_base'
    source_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding = mapped_column(Vector(1536))
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


# --- Module 2 / Module 3 tables (included for completeness per ARCHITECTURE.md §3.1) ---

class InterviewSession(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'in_progress', 'paused', 'completed', 'abandoned')"
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    skill_gap_report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("skill_gap_reports.id")
    )
    status: Mapped[str] = mapped_column(default="created")
    question_set: Mapped[dict] = mapped_column(JSONB, default=dict)
    current_turn_number: Mapped[int] = mapped_column(default=0)
    config: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {"max_turns": 12, "allow_follow_ups": True}
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint("session_id", "turn_number"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    turn_number: Mapped[int] = mapped_column(nullable=False)
    question: Mapped[dict] = mapped_column(JSONB, nullable=False)
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    answer_submitted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[str] = mapped_column(default="pending")
    evaluation: Mapped[dict | None] = mapped_column(JSONB)
    parent_turn_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interview_turns.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class AnswerEvaluationORM(Base):
    __tablename__ = "answer_evaluations"
    __table_args__ = (
        CheckConstraint("overall_score BETWEEN 0.0 AND 10.0"),
        CheckConstraint("weighted_score BETWEEN 0.0 AND 10.0"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_turns.id", ondelete="CASCADE")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    dimension_scores: Mapped[list] = mapped_column(JSONB, nullable=False)
    overall_score: Mapped[float]
    weighted_score: Mapped[float]
    summary_feedback: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[list] = mapped_column(JSONB, default=list)
    improvements: Mapped[list] = mapped_column(JSONB, default=list)
    routing_hint: Mapped[str] = mapped_column(nullable=False)
    suggested_follow_up: Mapped[str | None] = mapped_column(Text)
    skill_level_inferred: Mapped[str | None]
    evaluator_version: Mapped[str] = mapped_column(default="1.0.0")
    latency_ms: Mapped[int | None]
    evaluated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class FinalReport(Base):
    __tablename__ = "final_reports"
    __table_args__ = (CheckConstraint("overall_score BETWEEN 0.0 AND 10.0"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    overall_score: Mapped[float]
    readiness_level: Mapped[str | None]
    dimension_averages: Mapped[dict] = mapped_column(JSONB, default=dict)
    skill_progressions: Mapped[list] = mapped_column(JSONB, default=list)
    executive_summary: Mapped[str | None] = mapped_column(Text)
    top_strengths: Mapped[list] = mapped_column(JSONB, default=list)
    priority_gaps: Mapped[list] = mapped_column(JSONB, default=list)
    study_plan: Mapped[list] = mapped_column(JSONB, default=list)
    total_session_duration_seconds: Mapped[int | None]
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )