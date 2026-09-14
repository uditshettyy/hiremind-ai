# Phase 1 Handoff Documentation: Intake & Analysis Module

## 1. Phase 1 Summary

### Module Purpose & Overview
The **Intake & Analysis Module** (Module 1, owned by Person A) forms the entry point of the AI Interview Prep Platform. It ingests candidate resumes and job descriptions (JDs), parses them into structured representations using LLM extraction, stores chunked text and vector embeddings into Postgres/pgvector (`document_chunks`), and computes a structured skill-gap report comparing candidate qualifications against job requirements.

### Functions & Capabilities
1. `parse_resume`: Extracts raw text from PDF/DOCX resumes and uses LLM extraction to structure candidate skills, experience, and education (`ResumeProfile`).
2. `parse_jd`: Accepts raw Job Description text and structures role requirements, required proficiency levels, and priority weights (`ParsedJobDescription`).
3. `analyze_skill_gap`: Semantically compares candidate skills against JD requirements, computes gap severity (1-5 scale) and match scores, chunks and embeds resume & JD text for downstream RAG retrieval, and generates a canonical `SkillGapReport`.

### Exposed API Routes
The module exposes **exactly three HTTP POST endpoints** mounted at root level:
- `POST /parse/resume` — Accepts multipart file upload (`.pdf` or `.docx`), returns extracted text and structured profile.
- `POST /parse/jd` — Accepts JSON body `{"raw_text": "..."}`, returns structured requirements and role metadata.
- `POST /analyze/skill-gap` — Accepts candidate ID, job ID, raw resume text, and structured JD, returning a validated `SkillGapReport`.

### Output Data Schema
Output matches `SkillGapReport` defined in `app/core/schemas.py` and specified in `ARCHITECTURE.md` §2.1:
- `report_id` (`str`, UUIDv4)
- `candidate_id` (`str`)
- `job_id` (`str`)
- `generated_at` (`datetime`)
- `overall_match_score` (`float`, 0.0 to 1.0)
- `top_gaps` (`List[SkillGap]`, max 10 items ordered by `gap_severity` desc)
- `strengths` (`List[SkillGap]`, list of skills meeting or exceeding JD requirement)
- `metadata` (`dict`, extensibility hook)
- `@property primary_gap_skills` (`List[str]`, top 5 gap skill names)

### Corrections Applied in This Pass
- **Scope Creep Removed**: Removed non-conforming route prefixes (`/intake/...`) to align with exact `/parse/resume`, `/parse/jd`, and `/analyze/skill-gap` endpoint specifications. Cleaned up scratch scripts (`fix_table.py`).
- **Database Realignment**:
  - Configured `.env` to use local Postgres (`postgresql+asyncpg://postgres:postgres@localhost:5432/hiremind`), matching `docker-compose.yml` (`pgvector/pgvector:pg16`).
  - Re-aligned `app/core/models.py` to match `ARCHITECTURE.md` §3.1 schema exactly, correcting `DocumentChunk.embedding` vector dimension to `Vector(1536)` and restoring missing `created_at`, `generated_at`, and timestamp columns across all ORM models.
  - Added `init_db()` in `app/core/database.py` to guarantee `CREATE EXTENSION IF NOT EXISTS vector;` runs prior to table creation.

---

## 2. Phase 2 Context (Person B Ownership)

Person B (Module 2 owner) is separately developing the **Interview Agent Module** in their own branch. Their Phase 2 scope includes:
- A pgvector-based vector store + question bank (defining schema for questions, question embeddings, and question metadata).
- A question ingestion script to populate the question bank.
- A retrieval function that consumes skill-gap topics and retrieves the top-$k$ relevant interview questions per topic.

> [!IMPORTANT]
> The question bank tables, schemas, ingestion logic, and question retrieval functions belong **entirely to Person B**. Module 1 does NOT create, modify, or stub out any question bank tables or retrieval code.

---

## 3. How Phase 1 Connects to Phase 2

The integration between Phase 1 (Intake & Analysis) and Phase 2 (Interview Agent) is purely **data-driven**, not code-driven:
- **Handoff Artifact**: The `SkillGapReport` Pydantic model (`app/core/schemas.py`).
- **Data Flow**: Module 1 generates `SkillGapReport` and persists it to `skill_gap_reports`. Person B's Question Generator / RAG pipeline reads `SkillGapReport.top_gaps` and `SkillGapReport.primary_gap_skills` as topic inputs to retrieve targeted interview questions from their question bank.
- **Decoupled Architecture**: There are no shared database tables between question bank and skill gap reports, no shared functions, and zero direct imports between Module 1 and Module 2 logic.

---

## 4. Roadmap: Phase 3 (Evaluation & Reporting)

Person A's next module is **Module 3: Evaluation & Reporting**.

Key requirements for Phase 3:
- Must implement `evaluate_answer()` in `app/agents/evaluation/scorer.py`.
- **Contract Enforcement**: The function signature must match `ARCHITECTURE.md` §5.1 exactly:
  ```python
  async def evaluate_answer(
      *,
      turn: InterviewTurn,
      skill_gap_report: SkillGapReport,
      session_history: list[InterviewTurn],
      job_description_text: str,
      candidate_resume_text: str,
      model: str = "gpt-4o",
      temperature: float = 0.2,
      timeout_seconds: int = 30,
  ) -> AnswerEvaluation
  ```
- Person B's Interview Agent will call `evaluate_answer()` synchronously during the LangGraph execution loop for each candidate response.
