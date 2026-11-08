"""End-to-end test of the entire interview preparation and evaluation flow.

Verifies:
1. Document intake (parsing resume PDF + job description text).
2. Skill-gap report analysis (matching, gaps, scoring).
3. Question set & interview turn progression.
4. Per-turn scoring & routing evaluation (accuracy, depth, clarity, relevance, confidence).
5. Final performance report synthesis (executive summary, skill progression, study plan).
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.agents.evaluation.router import get_generate_structured as get_eval_llm
from app.agents.intake.router import get_generate_structured as get_intake_llm
from app.core.database import get_db
from tests.fixtures.fake_llm import fake_report_generate_structured, make_fake_generate_structured
from tests.fixtures.sample_session import (
    CANDIDATE_RESUME_TEXT,
    JOB_DESCRIPTION_TEXT,
    SKILL_GAP_REPORT,
    TURN_STRONG_TECHNICAL,
)

SCENARIO_MAP = {
    "q-indexing-1": "strong_technical",
    "q-conflict-1": "weak_behavioral_no_star",
    "q-incident-1": "mediocre_situational",
}


async def test_complete_interview_lifecycle_end_to_end(
    sample_resume_pdf_bytes,
    sample_jd_text,
    mock_generate_structured,
    mock_embed_fn,
    fake_db_session,
    monkeypatch,
):
    # Monkeypatch vector embeddings for intake chunking
    from app.agents.intake import router as intake_router_module
    monkeypatch.setattr(intake_router_module, "embed_texts", mock_embed_fn)

    # Prevent lifespan DB initialization during test
    async def fake_init_db():
        pass
    monkeypatch.setattr("app.core.database.init_db", fake_init_db)
    monkeypatch.setattr("app.main.init_db", fake_init_db)

    # Setup dependency overrides for LLM and DB across all modules
    app.dependency_overrides[get_intake_llm] = lambda: mock_generate_structured
    eval_fake = make_fake_generate_structured(SCENARIO_MAP)
    app.dependency_overrides[get_eval_llm] = lambda: eval_fake
    app.dependency_overrides[get_db] = lambda: fake_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            # -------------------------------------------------------------
            # STEP 1: Parse candidate resume
            # -------------------------------------------------------------
            resume_files = {
                "file": ("resume.pdf", sample_resume_pdf_bytes, "application/pdf")
            }
            resume_resp = await client.post("/parse/resume", files=resume_files)
            assert resume_resp.status_code == 200
            resume_data = resume_resp.json()
            assert "Jane Doe" in resume_data["resume_text"]
            assert resume_data["profile"]["name"] == "Jane Doe"

            # -------------------------------------------------------------
            # STEP 2: Parse job description
            # -------------------------------------------------------------
            jd_resp = await client.post("/parse/jd", json={"raw_text": sample_jd_text})
            assert jd_resp.status_code == 200
            jd_data = jd_resp.json()
            assert jd_data["title"] == "Senior Backend Engineer"
            assert len(jd_data["requirements"]) > 0

            # -------------------------------------------------------------
            # STEP 3: Analyze skill gap (Module 1 -> Module 2 Handoff)
            # -------------------------------------------------------------
            gap_resp = await client.post(
                "/analyze/skill-gap",
                json={
                    "candidate_id": "cand-test-e2e",
                    "job_id": "job-test-e2e",
                    "resume_text": resume_data["resume_text"],
                    "parsed_jd": jd_data,
                    "candidate_name": "Jane Doe",
                },
            )
            assert gap_resp.status_code == 200
            gap_report = gap_resp.json()
            assert "overall_match_score" in gap_report
            assert len(gap_report["top_gaps"]) > 0 or len(gap_report["strengths"]) > 0

            # -------------------------------------------------------------
            # STEP 4: Evaluate Candidate Answer (Module 2 -> Module 3)
            # -------------------------------------------------------------
            eval_payload = {
                "session_id": "sess-e2e-001",
                "turn": TURN_STRONG_TECHNICAL.model_dump(mode="json"),
                "skill_gap_report": SKILL_GAP_REPORT.model_dump(mode="json"),
                "session_history": [],
                "job_description_text": JOB_DESCRIPTION_TEXT,
                "candidate_resume_text": CANDIDATE_RESUME_TEXT,
            }
            eval_resp = await client.post("/evaluate/answer", json=eval_payload)
            assert eval_resp.status_code == 200
            eval_data = eval_resp.json()
            assert eval_data["overall_score"] >= 7.0
            assert eval_data["routing_hint"] in {
                "next_question",
                "skip_to_harder",
                "follow_up",
                "drill_deeper",
            }
            assert len(eval_data["dimension_scores"]) == 5

            # -------------------------------------------------------------
            # STEP 5: Generate Final Comprehensive Performance Report
            # -------------------------------------------------------------
            app.dependency_overrides[get_eval_llm] = lambda: fake_report_generate_structured

            evaluated_turn = TURN_STRONG_TECHNICAL.model_dump(mode="json")
            evaluated_turn["evaluation"] = eval_data
            evaluated_turn["status"] = "evaluated"

            report_payload = {
                "session_id": "sess-e2e-001",
                "candidate_id": "cand-test-e2e",
                "job_id": "job-test-e2e",
                "turns": [evaluated_turn],
                "skill_gap_report": SKILL_GAP_REPORT.model_dump(mode="json"),
                "total_session_duration_seconds": 600,
            }
            final_resp = await client.post("/report/generate", json=report_payload)
            assert final_resp.status_code == 200
            final_report = final_resp.json()

            # Validate comprehensive report shape
            assert final_report["overall_score"] >= 7.0
            assert final_report["readiness_level"] in {"ready", "needs_work", "not_ready"}
            assert len(final_report["dimension_averages"]) == 5
            assert len(final_report["study_plan"]) >= 1
            assert len(final_report["top_strengths"]) >= 1
            assert final_report["executive_summary"] != ""
            assert len(final_report["per_turn_evaluations"]) == 1

        finally:
            app.dependency_overrides.clear()
