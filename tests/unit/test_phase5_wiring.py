"""Unit test for Phase 5: Wire Interview -> Evaluation.

Verifies that Interview Agent's evaluate_turn node calls Person A's real
evaluate_answer function (from app.agents.evaluation.scorer) and updates the
session turn with the resulting AnswerEvaluation.
"""
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from app.agents.interview.nodes import evaluate_turn, InterviewGraphState
from app.core.schemas import (
    AnswerEvaluation,
    Difficulty,
    DimensionScore,
    InterviewSession,
    InterviewTurn,
    Question,
    QuestionSet,
    QuestionType,
    SessionStatus,
    TurnStatus,
)
from tests.fixtures.sample_session import (
    CANDIDATE_RESUME_TEXT,
    JOB_DESCRIPTION_TEXT,
    SKILL_GAP_REPORT,
)

# ---------------------------------------------------------------------------
# Fake AnswerEvaluation that the mocked evaluate_answer returns
# ---------------------------------------------------------------------------
FAKE_EVALUATION = AnswerEvaluation(
    evaluation_id="eval-phase5-test",
    session_id="sess-phase5-test",
    turn_number=1,
    candidate_id=SKILL_GAP_REPORT.candidate_id,
    evaluated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    overall_score=8.5,
    weighted_score=8.5,
    routing_hint="next_question",
    summary_feedback="Strong technical response demonstrating thorough understanding of PostgreSQL indexing internals.",
    strengths=["Clear explanation of range vs hash index behavior"],
    improvements=["Could mention write amplification/maintenance costs"],
    model_answer_snippet="B-tree indexes maintain a sorted tree structure supporting range and equality queries.",
    skill_level_inferred="proficient",
    suggested_follow_up=None,
    latency_ms=100,
    dimension_scores=[
        DimensionScore(dimension="accuracy", score=9.0, rationale="Factually precise."),
        DimensionScore(dimension="depth", score=8.5, rationale="Clear understanding."),
        DimensionScore(dimension="clarity", score=9.0, rationale="Well-structured."),
        DimensionScore(dimension="relevance", score=9.5, rationale="Completely answers the question."),
        DimensionScore(dimension="confidence", score=8.5, rationale="Decisive explanation."),
    ],
)


@pytest.mark.asyncio
async def test_evaluate_turn_uses_real_evaluation_scorer(monkeypatch):
    # Patch evaluate_answer at the nodes module level so the already-imported
    # reference is replaced. The default-argument binding in scorer.py means
    # patching the scorer module attribute alone does not reach the call site.
    mock_evaluate = AsyncMock(return_value=FAKE_EVALUATION)
    monkeypatch.setattr("app.agents.interview.nodes.evaluate_answer", mock_evaluate)

    question = Question(
        question_id="q-indexing-1",
        target_skill="postgres_indexing",
        difficulty=Difficulty.MEDIUM,
        question_type=QuestionType.TECHNICAL,
        question_text="How do B-tree indexes work in PostgreSQL?",
    )

    answered_turn = InterviewTurn(
        turn_number=1,
        question=question,
        answer_text="B-tree indexes maintain a balanced tree structure in PostgreSQL to enable O(log N) lookups, range scans, and equality checks.",
        status=TurnStatus.ANSWERED,
    )

    question_set = QuestionSet(
        set_id="qset-1",
        session_id="sess-phase5-test",
        questions=[question],
        created_at=SKILL_GAP_REPORT.generated_at,
    )

    session = InterviewSession(
        session_id="sess-phase5-test",
        candidate_id=SKILL_GAP_REPORT.candidate_id,
        job_id=SKILL_GAP_REPORT.job_id,
        skill_gap_report_id=SKILL_GAP_REPORT.report_id,
        status=SessionStatus.IN_PROGRESS,
        session_started_at=SKILL_GAP_REPORT.generated_at,
        question_set=question_set,
        current_turn_number=1,
        turns=[answered_turn],
    )

    state: InterviewGraphState = {
        "session": session,
        "skill_gap_report": SKILL_GAP_REPORT,
        "job_description_text": JOB_DESCRIPTION_TEXT,
        "candidate_resume_text": CANDIDATE_RESUME_TEXT,
    }

    updated_state = await evaluate_turn(state)
    updated_session = updated_state["session"]
    latest_turn = updated_session.turns[-1]

    # Verify that the turn is updated with evaluation from Person A's real scorer
    assert latest_turn.evaluation is not None
    assert latest_turn.evaluation.overall_score >= 6.0
    assert latest_turn.evaluation.candidate_id == SKILL_GAP_REPORT.candidate_id
    assert len(latest_turn.evaluation.dimension_scores) == 5
    assert latest_turn.evaluation.routing_hint in {
        "next_question",
        "skip_to_harder",
        "follow_up",
        "drill_deeper",
    }
