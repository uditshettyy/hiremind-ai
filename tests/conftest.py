"""Shared fixtures for the intake module's tests."""
from __future__ import annotations

import io

import pytest


SAMPLE_RESUME_TEXT = """Jane Doe
jane.doe@example.com

Summary: Backend engineer with 4 years building Python services.

Experience:
Senior Software Engineer, Acme Corp (2022-Present)
Built and maintained FastAPI microservices handling 10k req/s. Owned the
team's PostgreSQL schema design and query optimization.

Software Engineer, Beta Inc (2020-2022)
Wrote Python data pipelines using pandas and Airflow.

Skills: Python, FastAPI, PostgreSQL, Docker, pandas, Airflow

Education:
B.S. Computer Science, State University, 2020
"""

SAMPLE_JD_TEXT = """Senior Backend Engineer — NovaTech

Requirements:
- 5+ years of professional Python development
- Expert-level experience with Kubernetes in production
- Strong PostgreSQL skills, including query optimization
- Familiarity with FastAPI or a similar async framework

Preferred:
- Experience with MLOps tooling
"""


@pytest.fixture
def sample_resume_text() -> str:
    return SAMPLE_RESUME_TEXT


@pytest.fixture
def sample_jd_text() -> str:
    return SAMPLE_JD_TEXT


@pytest.fixture
def sample_resume_pdf_bytes() -> bytes:
    """A real, parseable single-page PDF built with PyMuPDF — not a mock."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), SAMPLE_RESUME_TEXT)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


@pytest.fixture
def sample_resume_docx_bytes() -> bytes:
    """A real, parseable .docx built with python-docx — not a mock."""
    import docx

    document = docx.Document()
    for line in SAMPLE_RESUME_TEXT.splitlines():
        document.add_paragraph(line)
    buf = io.BytesIO()
    document.save(buf)
    return buf.getvalue()


# --- Canned LLM responses, keyed by the response_model class name that
# generate_structured() is called with. Only the LLM call is mocked — every
# validation path (Pydantic, our own normalization code) still runs for real.
_FIXTURES = {
    "ResumeProfile": {
        "name": "Jane Doe",
        "summary": "Backend engineer with 4 years building Python services.",
        "skills": [
            {"skill_name": "Python", "category": "technical", "proficiency": "proficient",
             "evidence": "4 years building Python services"},
            {"skill_name": "PostgreSQL", "category": "technical", "proficiency": "competent",
             "evidence": "Owned the team's PostgreSQL schema design"},
            {"skill_name": "Kubernetes", "category": "tool", "proficiency": "absent"},
        ],
        "experience": ["Senior Software Engineer, Acme Corp (2022-Present)"],
        "projects": [],
        "education": ["B.S. Computer Science, State University, 2020"],
    },
    "ParsedJobDescription": {
        "title": "Senior Backend Engineer",
        "company": "NovaTech",
        "requirements": [
            {"skill_name": "Python", "category": "technical", "required_level": "expert",
             "priority": 5, "evidence": "5+ years of professional Python development"},
            {"skill_name": "Kubernetes", "category": "tool", "required_level": "expert",
             "priority": 5, "evidence": "Expert-level experience with Kubernetes in production"},
            {"skill_name": "PostgreSQL", "category": "technical", "required_level": "proficient",
             "priority": 4, "evidence": "Strong PostgreSQL skills, including query optimization"},
        ],
        "responsibilities": [],
        "raw_text": SAMPLE_JD_TEXT,
    },
    "RawSkillGapAnalysis": {
        "overall_match_score": 0.5,
        "top_gaps": [
            {"skill_name": "Kubernetes", "category": "tool",
             "jd_required_level": "expert", "resume_claimed_level": "absent",
             "gap_level": "expert", "gap_severity": 5,
             "jd_evidence": "Expert-level experience with Kubernetes in production",
             "resume_evidence": None,
             "suggested_focus": "Be ready to discuss any Kubernetes exposure you have, even minimal."},
        ],
        "strengths": [
            {"skill_name": "Python", "category": "technical",
             "jd_required_level": "expert", "resume_claimed_level": "proficient",
             "gap_level": "expert", "gap_severity": 1,
             "jd_evidence": "5+ years of professional Python development",
             "resume_evidence": "4 years building Python services",
             "suggested_focus": "Highlight your production FastAPI work."},
        ],
        "metadata": {},
    },
}


@pytest.fixture
def mock_generate_structured():
    """Returns an async callable matching generate_structured's signature.

    Looks up a canned response by response_model.__name__ and validates it
    through the real model — so a bug in your Pydantic models still fails
    the test, only the network call is faked.
    """
    async def _mock(*, system_prompt: str, user_prompt: str, response_model, **kwargs):
        data = _FIXTURES[response_model.__name__]
        return response_model.model_validate(data)

    return _mock


@pytest.fixture
def mock_embed_fn():
    """Fake embed_fn matching embed_texts' signature — no real API call."""
    async def _mock(texts):
        return [[0.0] * 1536 for _ in texts]

    return _mock


class FakeAsyncSession:
    """Minimal stand-in for AsyncSession — enough for _chunk_and_embed's add()/flush()."""

    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


@pytest.fixture
def fake_db_session():
    return FakeAsyncSession()