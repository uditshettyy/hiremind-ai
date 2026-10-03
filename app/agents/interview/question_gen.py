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

    Given a SkillGapReport, build a personalized QuestionSet that:
    1. Prioritizes technical questions based on skill gaps.
    2. Includes project deep-dive questions when space is available.
    3. Includes behavioral questions when space is available.
    4. Uses the existing pgvector RAG retrieval for all questions.
    """

    questions: List[Question] = []
    seen_ids = set()

    def add_question(
        result: QuestionBankSearchResult,
        target_skill: str,
        difficulty: Optional[Difficulty] = None,
    ) -> None:
        if result.question.id in seen_ids:
            return

        seen_ids.add(result.question.id)

        questions.append(
            Question(
                question_id=str(uuid.uuid4()),
                question_text=result.question.question_text,
                question_type=result.question.question_type,
                target_skill=target_skill,
                target_skill_gap_id=None,
                difficulty=difficulty or result.question.difficulty,
                expected_bullet_points=result.question.expected_bullet_points,
                max_duration_seconds=result.question.max_duration_seconds,
                source_chunks=[str(result.question.id)],
            )
        )

    # ---------------------------------------------------------------
    # Priority 1: Technical questions based on skill gaps
    # ---------------------------------------------------------------
    for gap in gap_report.top_gaps:
        if len(questions) >= max_total_questions:
            break

        results = await retrieve_questions_for_gap(
            db=db,
            openai_client=openai_client,
            skill_topic=gap.skill_name,
            top_k=top_k_per_gap,
        )

        for result in results:
            if len(questions) >= max_total_questions:
                break

            # Technical gap questions are the primary personalized
            # questions. Other categories retrieved by similarity are
            # still allowed here.
            add_question(
                result=result,
                target_skill=gap.skill_name,
            )

    # ---------------------------------------------------------------
    # Priority 2: Ensure project deep-dive coverage
    # ---------------------------------------------------------------
    if len(questions) < max_total_questions and gap_report.top_gaps:
        target_skill = gap_report.top_gaps[0].skill_name

        results = await retrieve_questions_for_gap(
            db=db,
            openai_client=openai_client,
            skill_topic=target_skill,
            top_k=2,
            category_filter="project-deep-dive",
        )

        for result in results:
            if len(questions) >= max_total_questions:
                break

            add_question(
                result=result,
                target_skill=target_skill,
            )

    # ---------------------------------------------------------------
    # Priority 3: Ensure behavioral coverage
    # ---------------------------------------------------------------
    if len(questions) < max_total_questions:
        target_skill = (
            gap_report.top_gaps[0].skill_name
            if gap_report.top_gaps
            else "general"
        )

        results = await retrieve_questions_for_gap(
            db=db,
            openai_client=openai_client,
            skill_topic=target_skill,
            top_k=2,
            category_filter="behavioral",
        )

        for result in results:
            if len(questions) >= max_total_questions:
                break

            add_question(
                result=result,
                target_skill=target_skill,
            )

    # ---------------------------------------------------------------
    # Priority 4: Strength-reinforcement questions
    # ---------------------------------------------------------------
    remaining = max_total_questions - len(questions)

    if remaining > 0:
        for strength in gap_report.strengths[:remaining]:
            results = await retrieve_questions_for_gap(
                db=db,
                openai_client=openai_client,
                skill_topic=strength.skill_name,
                top_k=1,
            )

            for result in results:
                if len(questions) >= max_total_questions:
                    break

                if result.question.id in seen_ids:
                    continue

                add_question(
                    result=result,
                    target_skill=strength.skill_name,
                    difficulty=Difficulty.EASY,
                )

                break

    return QuestionSet(
        set_id=str(uuid.uuid4()),
        session_id="",
        questions=questions,
        created_at=datetime.utcnow(),
    )