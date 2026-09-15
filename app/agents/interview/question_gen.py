# app/agents/interview/question_gen.py
"""
RAG-based question generator for the Interview Agent (Module 2).
Consumes SkillGapReport → queries pgvector question_bank → returns QuestionSet.
"""
import uuid
from typing import List, Dict, Optional
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from openai import AsyncOpenAI

from app.core.schemas import (
    SkillGapReport,
    Question,
    QuestionSet,
    QuestionBankSearchResult,
    QuestionBankItem,
    QuestionType,
    Difficulty,
)


# ── Config ──────────────────────────────────────────────────────────
EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_TOP_K = 3


# ── Embedding Helper ────────────────────────────────────────────────


async def embed_text(client: AsyncOpenAI, text: str) -> List[float]:
    """Embed a single text string."""
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0].embedding


# ── Core Retrieval ──────────────────────────────────────────────────


async def retrieve_questions_for_gap(
    db: AsyncSession,
    openai_client: AsyncOpenAI,
    skill_topic: str,
    top_k: int = DEFAULT_TOP_K,
    category_filter: Optional[str] = None,
    difficulty_filter: Optional[str] = None,
) -> List[QuestionBankSearchResult]:
    """
    Retrieve top-k questions most similar to a single skill-gap topic.
    Uses cosine similarity over pgvector.
    """
    # 1. Embed the skill topic
    query_embedding = await embed_text(openai_client, skill_topic)

    # 2. Build dynamic SQL with optional filters
    #    We use raw SQL because pgvector's <=> operator is cleanest this way.
    filters = []
    params = {
        "embedding": str(query_embedding),  # pgvector accepts stringified array
        "top_k": top_k,
    }

    if category_filter:
        filters.append("AND category = :category")
        params["category"] = category_filter

    if difficulty_filter:
        filters.append("AND difficulty = :difficulty")
        params["difficulty"] = difficulty_filter

    where_clause = "\n".join(filters)

    stmt = text(f"""
        SELECT
            id,
            question_text,
            category,
            question_type,
            difficulty,
            target_skills,
            expected_bullet_points,
            max_duration_seconds,
            metadata,
            created_at,
            1 - (embedding <=> :embedding) AS similarity_score
        FROM question_bank
        WHERE embedding IS NOT NULL
        {where_clause}
        ORDER BY embedding <=> :embedding
        LIMIT :top_k
    """)

    result = await db.execute(stmt, params)
    rows = result.mappings().all()

    return [
        QuestionBankSearchResult(
            question=QuestionBankItem(
                id=row["id"],
                question_text=row["question_text"],
                category=row["category"],
                question_type=QuestionType(row["question_type"]),
                difficulty=Difficulty(row["difficulty"]),
                target_skills=row["target_skills"],
                expected_bullet_points=row["expected_bullet_points"],
                max_duration_seconds=row["max_duration_seconds"],
                metadata=row["metadata"],
                created_at=row["created_at"],
            ),
            similarity_score=row["similarity_score"],
        )
        for row in rows
    ]


async def build_question_set_from_gaps(
    db: AsyncSession,
    openai_client: AsyncOpenAI,
    gap_report: SkillGapReport,
    top_k_per_gap: int = 2,
    max_total_questions: int = 10,
) -> QuestionSet:
    """
    Main entrypoint called by the LangGraph INIT node.
    Given a SkillGapReport, return a curated QuestionSet ordered by gap severity.
    """
    questions: List[Question] = []
    seen_ids = set()

    # Priority 1: Target the top_gaps (highest severity first)
    for gap in gap_report.top_gaps:
        topic = gap.skill_name  # e.g. "system-design", "python"
        results = await retrieve_questions_for_gap(
            db=db,
            openai_client=openai_client,
            skill_topic=topic,
            top_k=top_k_per_gap,
            # Optional: you can filter by difficulty based on gap.gap_level
            # difficulty_filter="hard" if gap.gap_severity >= 4 else "medium",
        )

        for r in results:
            if r.question.id in seen_ids:
                continue
            seen_ids.add(r.question.id)

            questions.append(
                Question(
                    question_id=str(uuid.uuid4()),
                    question_text=r.question.question_text,
                    question_type=r.question.question_type,
                    target_skill=topic,
                    target_skill_gap_id=None,  # populated later if you link to gap UUID
                    difficulty=r.question.difficulty,
                    expected_bullet_points=r.question.expected_bullet_points,
                    max_duration_seconds=r.question.max_duration_seconds,
                    source_chunks=[str(r.question.id)],  # audit trail: which bank item
                )
            )

            if len(questions) >= max_total_questions:
                break

        if len(questions) >= max_total_questions:
            break

    # Priority 2: If we have room, add strength-reinforcement questions
    # (softball questions on things they already know well — builds confidence)
    remaining = max_total_questions - len(questions)
    if remaining > 0:
        for strength in gap_report.strengths[:remaining]:
            results = await retrieve_questions_for_gap(
                db=db,
                openai_client=openai_client,
                skill_topic=strength.skill_name,
                top_k=1,
            )
            for r in results:
                if r.question.id not in seen_ids:
                    seen_ids.add(r.question.id)
                    questions.append(
                        Question(
                            question_id=str(uuid.uuid4()),
                            question_text=r.question.question_text,
                            question_type=QuestionType.BEHAVIORAL
                            if r.question.category == "behavioral"
                            else QuestionType.TECHNICAL,
                            target_skill=strength.skill_name,
                            difficulty=Difficulty.EASY,  # strengths get easier questions
                            expected_bullet_points=r.question.expected_bullet_points,
                            source_chunks=[str(r.question.id)],
                        )
                    )
                    break

    return QuestionSet(
        set_id=str(uuid.uuid4()),
        session_id="",  # populated by caller (graph.py)
        questions=questions,
        created_at=datetime.utcnow(),
    )