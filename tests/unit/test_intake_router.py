"""Tests through the actual FastAPI app — catches DI/wiring bugs unit tests can't.

Overrides get_generate_structured and get_db via app.dependency_overrides,
and monkeypatches embed_texts at its import location in router.py (it's
called directly there, not injected via Depends).
"""
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.agents.intake import router as intake_router_module
from app.agents.intake.router import get_generate_structured, router
from app.core.database import get_db


@pytest.fixture
def app(mock_generate_structured, mock_embed_fn, fake_db_session, monkeypatch):
    test_app = FastAPI()
    test_app.include_router(router)

    test_app.dependency_overrides[get_generate_structured] = lambda: mock_generate_structured
    test_app.dependency_overrides[get_db] = lambda: fake_db_session

    monkeypatch.setattr(intake_router_module, "embed_texts", mock_embed_fn)

    return test_app


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_parse_resume_route(client, sample_resume_pdf_bytes):
    files = {"file": ("resume.pdf", sample_resume_pdf_bytes, "application/pdf")}
    resp = await client.post("/parse/resume", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert "Jane Doe" in body["resume_text"]
    assert body["profile"]["name"] == "Jane Doe"


async def test_parse_resume_route_rejects_bad_extension(client):
    files = {"file": ("resume.txt", b"hello", "text/plain")}
    resp = await client.post("/parse/resume", files=files)
    assert resp.status_code == 415


async def test_parse_jd_route(client, sample_jd_text):
    resp = await client.post("/parse/jd", json={"raw_text": sample_jd_text})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Senior Backend Engineer"


async def test_parse_jd_route_rejects_empty_text(client):
    resp = await client.post("/parse/jd", json={"raw_text": "   "})
    assert resp.status_code == 400


from app.agents.intake.service import parse_or_gen_uuid


async def test_analyze_skill_gap_route(client, sample_resume_text, sample_jd_text):
    parsed_jd_payload = {
        "title": "Senior Backend Engineer",
        "company": "NovaTech",
        "requirements": [],
        "responsibilities": [],
        "raw_text": sample_jd_text,
    }
    resp = await client.post(
        "/analyze/skill-gap",
        json={
            "candidate_id": "cand-123",
            "job_id": "job-456",
            "resume_text": sample_resume_text,
            "parsed_jd": parsed_jd_payload,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    cand_uuid = str(parse_or_gen_uuid("cand-123", "candidate"))
    job_uuid = str(parse_or_gen_uuid("job-456", "job"))
    assert body["candidate_id"] == cand_uuid
    assert body["job_id"] == job_uuid


async def test_routes_return_503_when_llm_not_wired(sample_jd_text, fake_db_session):
    """Without overriding get_generate_structured, it falls back to the real
    dependency — here we verify the None fallback path degrades to 503."""
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_generate_structured] = lambda: None
    test_app.dependency_overrides[get_db] = lambda: fake_db_session

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        resp = await c.post("/parse/jd", json={"raw_text": sample_jd_text})
    assert resp.status_code == 503