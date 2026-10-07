"""Unit tests for Module 1's core logic, per ARCHITECTURE.md §8.7."""
import pytest

from app.agents.intake import gap_analyzer, parser, service
from app.agents.intake.jd_parser import ParsedJobDescription, parse_job_description
from app.agents.intake.parser import (
    ResumeParseError,
    extract_resume_text,
    parse_resume,
)
from app.core.schemas import ProficiencyLevel, SkillGap


# --- Text extraction (real PDF/DOCX bytes, no mocking) ---

def test_extract_resume_text_from_pdf(sample_resume_pdf_bytes):
    text = extract_resume_text("resume.pdf", sample_resume_pdf_bytes)
    assert "Jane Doe" in text
    assert "Python" in text


def test_extract_resume_text_from_docx(sample_resume_docx_bytes):
    text = extract_resume_text("resume.docx", sample_resume_docx_bytes)
    assert "Jane Doe" in text


def test_extract_resume_text_rejects_unsupported_type():
    with pytest.raises(ResumeParseError):
        extract_resume_text("resume.txt", b"whatever")


def test_extract_resume_text_rejects_empty_pdf():
    import fitz

    doc = fitz.open()
    doc.new_page()  # blank page, no text
    buf = __import__("io").BytesIO()
    doc.save(buf)
    doc.close()
    with pytest.raises(ResumeParseError):
        extract_resume_text("resume.pdf", buf.getvalue())


# --- Resume structuring (mocked LLM) ---

async def test_parse_resume_end_to_end(sample_resume_pdf_bytes, mock_generate_structured):
    text, profile = await parse_resume("resume.pdf", sample_resume_pdf_bytes, mock_generate_structured)
    assert "Jane Doe" in text
    assert profile.name == "Jane Doe"
    assert any(s.skill_name == "Python" for s in profile.skills)


async def test_parse_resume_without_llm_callable_raises(sample_resume_pdf_bytes):
    with pytest.raises(RuntimeError):
        await parse_resume("resume.pdf", sample_resume_pdf_bytes, generate_structured=None)


# --- JD structuring (mocked LLM) ---

async def test_parse_jd_end_to_end(sample_jd_text, mock_generate_structured):
    parsed = await parse_job_description(sample_jd_text, mock_generate_structured)
    assert parsed.title == "Senior Backend Engineer"
    assert parsed.raw_text == sample_jd_text  # raw_text must be the original input, not the LLM's echo
    assert all(
        isinstance(r.required_level, ProficiencyLevel) for r in parsed.requirements
    )


async def test_parse_jd_rejects_empty_text(mock_generate_structured):
    with pytest.raises(ValueError):
        await parse_job_description("   ", mock_generate_structured)


async def test_parse_jd_without_llm_callable_raises(sample_jd_text):
    with pytest.raises(RuntimeError):
        await parse_job_description(sample_jd_text, generate_structured=None)


# --- Gap analysis (mocked LLM) ---

async def test_build_skill_gap_report_normalizes_identity_fields(
    sample_resume_text, sample_jd_text, mock_generate_structured
):
    parsed_jd = ParsedJobDescription(
        title="Senior Backend Engineer", company="NovaTech",
        requirements=[], responsibilities=[], raw_text=sample_jd_text,
    )
    report = await gap_analyzer.build_skill_gap_report(
        candidate_id="cand-123",
        job_id="job-456",
        resume_text=sample_resume_text,
        parsed_jd=parsed_jd,
        generate_structured=mock_generate_structured,
    )
    # These must be overwritten by our own code, not trusted from the LLM —
    # the fixture deliberately returns "placeholder" for all three.
    assert report.candidate_id == "cand-123"
    assert report.job_id == "job-456"
    assert report.report_id != "placeholder"
    assert report.generated_at.year >= 2026


async def test_build_skill_gap_report_caps_and_sorts_top_gaps(
    sample_resume_text, sample_jd_text
):
    many_gaps = [
        SkillGap(
            skill_name=f"skill-{i}", category="technical",
            jd_required_level=ProficiencyLevel.EXPERT,
            resume_claimed_level=ProficiencyLevel.ABSENT,
            gap_level=ProficiencyLevel.EXPERT,
            gap_severity=(i % 5) + 1,
            jd_evidence="evidence", suggested_focus="focus",
        )
        for i in range(15)
    ]

    async def mock_llm(*, system_prompt, user_prompt, response_model, **kwargs):
        # Build via the actual response_model passed in (RawSkillGapAnalysis
        # — no max_length cap, no id/timestamp fields) rather than assuming
        # SkillGapReport's shape.
        return response_model(overall_match_score=0.3, top_gaps=many_gaps, strengths=[])

    parsed_jd = ParsedJobDescription(raw_text=sample_jd_text, requirements=[])
    report = await gap_analyzer.build_skill_gap_report(
        candidate_id="c", job_id="j", resume_text=sample_resume_text,
        parsed_jd=parsed_jd, generate_structured=mock_llm,
    )
    assert len(report.top_gaps) == 10  # capped per SkillGapReport's max_length
    severities = [g.gap_severity for g in report.top_gaps]
    assert severities == sorted(severities, reverse=True)


async def test_build_skill_gap_report_without_llm_callable_raises(
    sample_resume_text, sample_jd_text
):
    parsed_jd = ParsedJobDescription(raw_text=sample_jd_text, requirements=[])
    with pytest.raises(RuntimeError):
        await gap_analyzer.build_skill_gap_report(
            candidate_id="c", job_id="j", resume_text=sample_resume_text,
            parsed_jd=parsed_jd, generate_structured=None,
        )


# --- service.py orchestration: chunk/embed wiring ---

async def test_analyze_skill_gap_writes_document_chunks_when_wired(
    sample_resume_text, sample_jd_text, mock_generate_structured, mock_embed_fn, fake_db_session,
):
    parsed_jd = ParsedJobDescription(
        title="Senior Backend Engineer", requirements=[], raw_text=sample_jd_text,
    )
    await service.analyze_skill_gap(
        candidate_id="cand-123", job_id="job-456",
        resume_text=sample_resume_text, parsed_jd=parsed_jd,
        generate_structured=mock_generate_structured,
        db_session=fake_db_session, embed_fn=mock_embed_fn,
    )
    added_source_types = {chunk.source_type for chunk in fake_db_session.added if hasattr(chunk, "source_type")}
    assert added_source_types == {"resume", "jd"}


async def test_analyze_skill_gap_no_ops_chunking_when_unwired(
    sample_resume_text, sample_jd_text, mock_generate_structured,
):
    """Confirms the Phase-1 no-op path (no db_session/embed_fn) still works —
    this is what lets earlier tests run without a real database."""
    parsed_jd = ParsedJobDescription(
        title="Senior Backend Engineer", requirements=[], raw_text=sample_jd_text,
    )
    report = await service.analyze_skill_gap(
        candidate_id="cand-123", job_id="job-456",
        resume_text=sample_resume_text, parsed_jd=parsed_jd,
        generate_structured=mock_generate_structured,
    )
    assert report.candidate_id == "cand-123"