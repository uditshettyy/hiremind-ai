"""LLM-based question generator fallback (no DB / no question bank).

Used by POST /session/bootstrap when pgvector is unavailable.
Generates a QuestionSet directly from the SkillGapReport using Groq.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.core.schemas import (
    Difficulty,
    Question,
    QuestionSet,
    QuestionType,
    SkillGapReport,
)
from app.utils.llm_client import generate_structured


_SYSTEM = """
You are an expert technical interviewer. Given a candidate's skill-gap analysis,
generate a targeted set of interview questions that probe the candidate's gaps
and verify their strengths.

Return a JSON object with EXACTLY this structure:
{
  "questions": [
    {
      "question_text": "Full interview question text",
      "question_type": "technical",
      "target_skill": "skill name",
      "difficulty": "medium"
    }
  ]
}

Rules:
- question_type must be one of: technical, behavioral, situational
- difficulty must be one of: easy, medium, hard
- Generate EXACTLY 5 questions total
- Weight heavily toward the top gaps (more severe gaps = more questions)
- Include at least 1 behavioral question
- Each question must be specific and actionable, not generic
"""


async def generate_questions_from_gaps(
    skill_gap_report: SkillGapReport,
    resume_text: str,
    job_description_text: str,
) -> QuestionSet:
    """Generate a QuestionSet directly from the LLM — no DB required."""

    gaps_summary = "\n".join(
        f"- {g.skill_name} (severity {g.gap_severity}/5, need: {g.jd_required_level}, have: {g.resume_claimed_level})"
        for g in skill_gap_report.top_gaps[:8]
    )
    strengths_summary = "\n".join(
        f"- {s.skill_name} (level: {s.resume_claimed_level})"
        for s in skill_gap_report.strengths[:5]
    )

    user_prompt = f"""CANDIDATE SKILL GAPS (prioritized):
{gaps_summary or 'No significant gaps identified.'}

CANDIDATE STRENGTHS:
{strengths_summary or 'No strengths listed.'}

JOB DESCRIPTION EXCERPT:
{job_description_text[:1500]}

RESUME EXCERPT:
{resume_text[:1500]}

Generate exactly 5 targeted interview questions as described.
"""

    result: Any = await generate_structured(
        system_prompt=_SYSTEM,
        user_prompt=user_prompt,
        timeout_seconds=60,
    )

    raw_questions: list[dict] = result.get("questions", []) if isinstance(result, dict) else []

    # Map LLM output to Question schema
    questions: list[Question] = []
    for item in raw_questions:
        try:
            q_type_raw = (item.get("question_type") or "technical").lower()
            q_type = QuestionType(q_type_raw) if q_type_raw in QuestionType._value2member_map_ else QuestionType.TECHNICAL

            diff_raw = (item.get("difficulty") or "medium").lower()
            difficulty = Difficulty(diff_raw) if diff_raw in Difficulty._value2member_map_ else Difficulty.MEDIUM

            questions.append(Question(
                question_id=str(uuid.uuid4()),
                question_text=item["question_text"],
                question_type=q_type,
                target_skill=item.get("target_skill", "general"),
                difficulty=difficulty,
            ))
        except (KeyError, ValueError):
            continue

    # Fallback: if LLM returned nothing usable, produce one generic question per top gap
    if not questions:
        for gap in skill_gap_report.top_gaps[:5]:
            questions.append(Question(
                question_id=str(uuid.uuid4()),
                question_text=f"Can you walk me through your experience with {gap.skill_name}? "
                              f"What's the most complex problem you've solved using it?",
                question_type=QuestionType.TECHNICAL,
                target_skill=gap.skill_name,
                difficulty=Difficulty.MEDIUM,
            ))

    now = datetime.now(timezone.utc)
    return QuestionSet(
        set_id=str(uuid.uuid4()),
        session_id="",   # filled in by bootstrap route
        questions=questions[:5],
        created_at=now,
    )

