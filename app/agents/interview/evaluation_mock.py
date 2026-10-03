"""
Temporary Evaluation Agent mock for Phase 3.

This matches the evaluation contract expected by the Interview Agent.
It will be replaced/wired to the real Module 3 scorer later.
"""

import uuid
from datetime import datetime, timezone

from app.core.schemas import (
    AnswerEvaluation,
    DimensionScore,
    InterviewTurn,
    ScoreDimension,
    SkillGapReport,
)


async def evaluate_answer(
    *,
    turn: InterviewTurn,
    skill_gap_report: SkillGapReport,
    session_history: list[InterviewTurn],
    job_description_text: str,
    candidate_resume_text: str,
    model: str = "mock-evaluator",
    temperature: float = 0.2,
    timeout_seconds: int = 30,
) -> AnswerEvaluation:
    """
    Temporary deterministic evaluator.

    Keeps the exact interface expected by the Interview Agent.
    """

    dimension_scores = [
        DimensionScore(
            dimension=ScoreDimension.ACCURACY,
            score=7.0,
            rationale="Mock evaluation: answer demonstrates reasonable technical understanding.",
        ),
        DimensionScore(
            dimension=ScoreDimension.DEPTH,
            score=6.5,
            rationale="Mock evaluation: answer contains useful detail but could go deeper.",
        ),
        DimensionScore(
            dimension=ScoreDimension.CLARITY,
            score=8.0,
            rationale="Mock evaluation: answer is reasonably clear and understandable.",
        ),
        DimensionScore(
            dimension=ScoreDimension.RELEVANCE,
            score=8.0,
            rationale="Mock evaluation: answer addresses the asked question.",
        ),
        DimensionScore(
            dimension=ScoreDimension.CONFIDENCE,
            score=7.0,
            rationale="Mock evaluation: response indicates reasonable confidence.",
        ),
    ]

    overall_score = sum(
        score.score for score in dimension_scores
    ) / len(dimension_scores)

    return AnswerEvaluation(
        evaluation_id=str(uuid.uuid4()),
        session_id="mock-session",
        turn_number=turn.turn_number,
        candidate_id="mock-candidate",
        evaluated_at=datetime.now(timezone.utc),
        dimension_scores=dimension_scores,
        overall_score=overall_score,
        weighted_score=overall_score,
        summary_feedback=(
            "Mock evaluation completed successfully. "
            "The answer was relevant and reasonably clear. "
            "A stronger response would provide more depth and concrete examples."
        ),
        strengths=[
            "Relevant response",
            "Clear explanation",
        ],
        improvements=[
            "Add more technical depth",
            "Include concrete examples",
        ],
        model_answer_snippet=None,
        routing_hint="next_question",
        suggested_follow_up=None,
        skill_level_inferred=None,
        evaluator_version="mock-1.0.0",
        latency_ms=1,
    )
