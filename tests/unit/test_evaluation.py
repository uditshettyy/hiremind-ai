import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root on path

import pytest

from app.core.exceptions import EvaluationError
from app.agents.evaluation.report_writer import generate_final_report
from app.agents.evaluation.scorer import evaluate_answer

from tests.fixtures.fake_llm import fake_report_generate_structured, make_fake_generate_structured
from tests.fixtures.sample_session import (
    CANDIDATE_RESUME_TEXT,
    JOB_DESCRIPTION_TEXT,
    SKILL_GAP_REPORT,
    TURN_MEDIOCRE_SITUATIONAL,
    TURN_STRONG_TECHNICAL,
    TURN_TOO_SHORT,
    TURN_WEAK_BEHAVIORAL,
)


SCENARIO_MAP = {
    "q-indexing-1": "strong_technical",
    "q-conflict-1": "weak_behavioral_no_star",
    "q-incident-1": "mediocre_situational",
}


@pytest.mark.asyncio
async def test_strong_technical_answer_scores_high_and_routes_forward():
    fake = make_fake_generate_structured(SCENARIO_MAP)
    result = await evaluate_answer(
        turn=TURN_STRONG_TECHNICAL,
        skill_gap_report=SKILL_GAP_REPORT,
        session_history=[],
        job_description_text=JOB_DESCRIPTION_TEXT,
        candidate_resume_text=CANDIDATE_RESUME_TEXT,
        _generate_structured=fake,
    )

    assert result.overall_score >= 8.0
    assert result.weighted_score > 0
    # gap_severity for postgres_indexing (a strength, severity=1) pulls weighted_score
    # slightly below overall_score via the severity_weight term.
    assert result.routing_hint in {"next_question", "skip_to_harder"}
    assert result.skill_level_inferred is not None
    assert len(result.dimension_scores) == 5
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_weak_behavioral_answer_scores_low_and_flags_star_gap():
    fake = make_fake_generate_structured(SCENARIO_MAP)
    result = await evaluate_answer(
        turn=TURN_WEAK_BEHAVIORAL,
        skill_gap_report=SKILL_GAP_REPORT,
        session_history=[TURN_STRONG_TECHNICAL],  # already-evaluated turn 1, unattached eval ok for history-only use
        job_description_text=JOB_DESCRIPTION_TEXT,
        candidate_resume_text=CANDIDATE_RESUME_TEXT,
        _generate_structured=fake,
    )

    assert result.overall_score < 5.0
    # weighted down further: conflict_resolution has gap_severity=3, medium difficulty -> near-neutral weight
    assert result.routing_hint in {"drill_deeper", "follow_up"}
    assert any("STAR" in i or "Situation" in i or "Action" in i for i in result.improvements)
    assert result.suggested_follow_up is not None


@pytest.mark.asyncio
async def test_mediocre_situational_answer_scores_middling():
    fake = make_fake_generate_structured(SCENARIO_MAP)
    result = await evaluate_answer(
        turn=TURN_MEDIOCRE_SITUATIONAL,
        skill_gap_report=SKILL_GAP_REPORT,
        session_history=[],
        job_description_text=JOB_DESCRIPTION_TEXT,
        candidate_resume_text=CANDIDATE_RESUME_TEXT,
        _generate_structured=fake,
    )

    assert 4.0 <= result.overall_score <= 7.5
    # incident_response has gap_severity=4 and difficulty=HARD -> weighted_score pushed up
    assert result.weighted_score >= result.overall_score * 0.95


@pytest.mark.asyncio
async def test_too_short_answer_raises_evaluation_error_without_calling_llm():
    def _unreachable(*args, **kwargs):
        raise AssertionError("LLM should never be called for a too-short answer")

    with pytest.raises(EvaluationError) as exc_info:
        await evaluate_answer(
            turn=TURN_TOO_SHORT,
            skill_gap_report=SKILL_GAP_REPORT,
            session_history=[],
            job_description_text=JOB_DESCRIPTION_TEXT,
            candidate_resume_text=CANDIDATE_RESUME_TEXT,
            _generate_structured=_unreachable,
        )
    assert exc_info.value.reason == "answer_too_short"


@pytest.mark.asyncio
async def test_missing_answer_text_raises_evaluation_error():
    empty_turn = TURN_TOO_SHORT.model_copy(update={"answer_text": "   "})
    with pytest.raises(EvaluationError) as exc_info:
        await evaluate_answer(
            turn=empty_turn,
            skill_gap_report=SKILL_GAP_REPORT,
            session_history=[],
            job_description_text=JOB_DESCRIPTION_TEXT,
            candidate_resume_text=CANDIDATE_RESUME_TEXT,
            _generate_structured=lambda **kw: (_ for _ in ()).throw(AssertionError("unreachable")),
        )
    assert exc_info.value.reason == "answer_too_short"


@pytest.mark.asyncio
async def test_malformed_llm_output_raises_evaluation_error():
    async def _bad(*, system_prompt, user_prompt, model, temperature):
        return {"dimension_scores": "not-a-list"}  # wrong shape

    with pytest.raises(EvaluationError) as exc_info:
        await evaluate_answer(
            turn=TURN_STRONG_TECHNICAL,
            skill_gap_report=SKILL_GAP_REPORT,
            session_history=[],
            job_description_text=JOB_DESCRIPTION_TEXT,
            candidate_resume_text=CANDIDATE_RESUME_TEXT,
            _generate_structured=_bad,
        )
    assert exc_info.value.reason == "unparseable_output"


@pytest.mark.asyncio
async def test_generate_final_report_aggregates_all_evaluated_turns():
    fake = make_fake_generate_structured(SCENARIO_MAP)

    evaluated = []
    for turn in (TURN_STRONG_TECHNICAL, TURN_WEAK_BEHAVIORAL, TURN_MEDIOCRE_SITUATIONAL):
        evaluation = await evaluate_answer(
            turn=turn,
            skill_gap_report=SKILL_GAP_REPORT,
            session_history=evaluated,
            job_description_text=JOB_DESCRIPTION_TEXT,
            candidate_resume_text=CANDIDATE_RESUME_TEXT,
            _generate_structured=fake,
        )
        turn = turn.model_copy(update={"evaluation": evaluation})
        evaluated.append(turn)

    report = await generate_final_report(
        session_id="sess-001",
        candidate_id="cand-001",
        job_id="job-001",
        turns=evaluated,
        skill_gap_report=SKILL_GAP_REPORT,
        total_session_duration_seconds=1800,
        _generate_structured=fake_report_generate_structured,
    )

    assert report.total_turns == 3
    assert len(report.per_turn_evaluations) == 3
    assert report.readiness_level in {"ready", "needs_work", "not_ready"}
    assert set(report.dimension_averages.keys())  # non-empty
    # incident_response (severity 4, no strengths gap entry) and conflict_resolution
    # (absent -> should show as a progression once inferred) both show up
    skills_covered = {p.skill_name for p in report.skill_progressions}
    assert "postgres_indexing" in skills_covered
    assert "conflict_resolution" in skills_covered
    assert "incident_response" in skills_covered
    assert len(report.study_plan) >= 1
    assert report.executive_summary


@pytest.mark.asyncio
async def test_generate_final_report_raises_when_no_evaluated_turns():
    from app.core.exceptions import ReportGenerationError

    with pytest.raises(ReportGenerationError):
        await generate_final_report(
            session_id="sess-empty",
            candidate_id="cand-001",
            job_id="job-001",
            turns=[TURN_STRONG_TECHNICAL],  # never had .evaluation attached
            skill_gap_report=SKILL_GAP_REPORT,
            total_session_duration_seconds=0,
            _generate_structured=fake_report_generate_structured,
        )


def test_evaluate_answer_route():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.agents.evaluation.router import get_generate_structured

    fake = make_fake_generate_structured(SCENARIO_MAP)
    app.dependency_overrides[get_generate_structured] = lambda: fake

    client = TestClient(app)
    payload = {
        "session_id": "sess-test-123",
        "turn": TURN_STRONG_TECHNICAL.model_dump(mode="json"),
        "skill_gap_report": SKILL_GAP_REPORT.model_dump(mode="json"),
        "session_history": [],
        "job_description_text": JOB_DESCRIPTION_TEXT,
        "candidate_resume_text": CANDIDATE_RESUME_TEXT,
    }

    response = client.post("/evaluate/answer", json=payload)
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-test-123"
    assert data["overall_score"] >= 8.0
    assert "routing_hint" in data


def test_generate_report_route():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.agents.evaluation.router import get_generate_structured

    fake_scorer = make_fake_generate_structured(SCENARIO_MAP)
    app.dependency_overrides[get_generate_structured] = lambda: fake_scorer

    client = TestClient(app)

    # First evaluate turn
    eval_resp = client.post("/evaluate/answer", json={
        "session_id": "sess-report-123",
        "turn": TURN_STRONG_TECHNICAL.model_dump(mode="json"),
        "skill_gap_report": SKILL_GAP_REPORT.model_dump(mode="json"),
        "session_history": [],
        "job_description_text": JOB_DESCRIPTION_TEXT,
        "candidate_resume_text": CANDIDATE_RESUME_TEXT,
    })
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()

    # Now override with report generator fake
    app.dependency_overrides[get_generate_structured] = lambda: fake_report_generate_structured

    evaluated_turn = TURN_STRONG_TECHNICAL.model_dump(mode="json")
    evaluated_turn["evaluation"] = eval_data
    evaluated_turn["status"] = "evaluated"

    report_payload = {
        "session_id": "sess-report-123",
        "candidate_id": "cand-001",
        "job_id": "job-001",
        "turns": [evaluated_turn],
        "skill_gap_report": SKILL_GAP_REPORT.model_dump(mode="json"),
        "total_session_duration_seconds": 600,
    }

    response = client.post("/report/generate", json=report_payload)
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "sess-report-123"
    assert data["overall_score"] >= 8.0
    assert "executive_summary" in data


