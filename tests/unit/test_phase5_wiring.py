"""Unit test for Phase 5: Wire Interview -> Evaluation.

Verifies that Interview Agent's evaluate_turn node calls Person A's real
evaluate_answer function (from app.agents.evaluation.scorer) and updates the
session turn with the resulting AnswerEvaluation.
"""
import pytest
from app.agents.interview.nodes import evaluate_turn, InterviewGraphState
from app.core.schemas import (
    Difficulty,
    InterviewSession,
    InterviewTurn,
    Question,
    QuestionSet,
    QuestionType,
    SessionStatus,
    TurnStatus,
)
from tests.fixtures.fake_llm import make_fake_generate_structured
from tests.fixtures.sample_session import (
    CANDIDATE_RESUME_TEXT,
    JOB_DESCRIPTION_TEXT,
    SKILL_GAP_REPORT,
)

SCENARIO_MAP = {
    "q-indexing-1": "strong_technical",
}


@pytest.mark.asyncio
async def test_evaluate_turn_uses_real_evaluation_scorer(monkeypatch):
    # Mock LLM underlying evaluate_answer
    fake_llm = make_fake_generate_structured(SCENARIO_MAP)
    monkeypatch.setattr(
        "app.agents.evaluation.scorer.default_generate_structured", fake_llm
    )

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
    assert latest_turn.evaluation.overall_score >= 7.0
    assert latest_turn.evaluation.candidate_id == SKILL_GAP_REPORT.candidate_id
    assert len(latest_turn.evaluation.dimension_scores) == 5
    assert latest_turn.evaluation.routing_hint in {
        "next_question",
        "skip_to_harder",
        "follow_up",
        "drill_deeper",
    }
