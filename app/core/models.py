from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base
from sqlalchemy.sql import func
import uuid


class QuestionBank(Base):
    __tablename__ = "question_bank"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)
    question_type = Column(String(50), nullable=False, default="technical")
    difficulty = Column(String(20), nullable=False, default="medium")
    target_skills = Column(ARRAY(String), nullable=False, default=list)
    expected_bullet_points = Column(JSON, default=list)
    max_duration_seconds = Column(Integer, default=180)
    embedding = Column(Vector(1536))
    extra_metadata = Column("metadata", JSON, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())