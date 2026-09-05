# ARCHITECTURE.md

**Project:** AI Interview Prep Platform
**Pattern:** FastAPI Modular Monolith
**Team:** 2-person split (Person A: Modules 1 & 3; Person B: Module 2)
**Last Updated:** 2026-09-02

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     FastAPI Modular Monolith                     │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐ │
│  │   Module 1   │   │   Module 2   │   │       Module 3        │ │
│  │  Intake &    │──▶│  Interview   │──▶│  Evaluation &         │ │
│  │  Analysis    │   │  Agent       │   │  Reporting            │ │
│  │  (Person A)  │   │  (Person B)  │   │  (Person A)           │ │
│  └──────────────┘   └──────────────┘   └──────────────────────┘ │
│         │                  ▲                     ▲               │
│         │                  │                     │               │
│         └──────────────────┴─────────────────────┘               │
│              Shared Pydantic Models + Postgres                   │
└─────────────────────────────────────────────────────────────────┘
```

### Handoff Contracts

| # | From → To | Artifact | Transport |
|---|---|---|---|
| 1 | Intake & Analysis → Interview Agent | `SkillGapReport` | Direct function call (in-memory) |
| 2 | Interview Agent → Evaluation & Reporting | `evaluate_answer()` | Direct function call (in-process) |
| 3 | Evaluation & Reporting → Interview Agent | `AnswerEvaluation` | Return value |

---

## 2. Pydantic Models

All models live in `app/core/schemas.py` and are imported by every module. No module defines its own version of a shared model.

### 2.1 Skill-Gap Report (Output of Module 1, Input to Module 2)

```python
from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from datetime import datetime


class ProficiencyLevel(str, Enum):
    """Canonical skill proficiency scale used across the system."""
    EXPERT = "expert"            # 5 — Can teach it
    PROFICIENT = "proficient"    # 4 — Can do it independently
    COMPETENT = "competent"      # 3 — Can do it with some help
    NOVICE = "novice"            # 2 — Basic exposure
    ABSENT = "absent"            # 1 — Not mentioned / no evidence


class SkillGap(BaseModel):
    """A single skill gap identified between resume and JD."""
    skill_name: str = Field(..., description="Canonical skill name (normalized)")
    category: str = Field(..., description="e.g., 'technical', 'soft', 'domain', 'tool'")
    jd_required_level: ProficiencyLevel
    resume_claimed_level: ProficiencyLevel
    gap_level: ProficiencyLevel = Field(
        ..., description="The delta: what the candidate needs to reach"
    )
    gap_severity: int = Field(
        ..., ge=1, le=5,
        description="1=minor, 5=critical (computed from level delta + JD priority)"
    )
    jd_evidence: str = Field(..., description="Quoted evidence from the JD")
    resume_evidence: Optional[str] = Field(
        None, description="Quoted evidence from resume, or null if absent"
    )
    suggested_focus: str = Field(
        ..., description="1-sentence coaching hint for the candidate"
    )


class SkillGapReport(BaseModel):
    """The complete skill-gap analysis delivered to the Interview Agent.

    This is **Handoff #1**. Person B's question generator consumes this directly.
    """
    report_id: str = Field(..., description="UUIDv4")
    candidate_id: str
    job_id: str
    generated_at: datetime
    overall_match_score: float = Field(..., ge=0.0, le=1.0)
    top_gaps: List[SkillGap] = Field(
        ..., max_length=10,
        description="Ordered by gap_severity desc. Interview Agent targets these first."
    )
    strengths: List[SkillGap] = Field(
        ..., description="Skills where resume >= JD requirement (positive reinforcement)"
    )
    metadata: dict = Field(default_factory=dict, description="Extensibility hook")

    @property
    def primary_gap_skills(self) -> List[str]:
        return [g.skill_name for g in self.top_gaps[:5]]
```

### 2.2 Question Set (Output of Module 2's RAG Generator)

```python
class QuestionType(str, Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    SITUATIONAL = "situational"
    FOLLOW_UP = "follow_up"      # Generated dynamically during the loop
    CLARIFYING = "clarifying"    # When the model needs more info


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class Question(BaseModel):
    """A single interview question with full provenance."""
    question_id: str = Field(..., description="UUIDv4")
    question_text: str
    question_type: QuestionType
    target_skill: str = Field(..., description="Which gap or strength this probes")
    target_skill_gap_id: Optional[str] = Field(
        None, description="FK to SkillGap if derived from gap report"
    )
    difficulty: Difficulty
    expected_bullet_points: List[str] = Field(
        default_factory=list,
        description="Rubric: what a strong answer should cover"
    )
    max_duration_seconds: int = Field(180, description="Recommended answer time limit")
    source_chunks: List[str] = Field(
        default_factory=list,
        description="pgvector chunk IDs used for RAG context (audit trail)"
    )


class QuestionSet(BaseModel):
    """The planned question sequence for a session. May be mutated by LangGraph."""
    set_id: str
    session_id: str
    questions: List[Question]
    created_at: datetime
```

### 2.3 Interview Turn / Session State (LangGraph State Machine)

```python
class TurnStatus(str, Enum):
    PENDING = "pending"        # Question asked, awaiting answer
    ANSWERED = "answered"      # Answer received, awaiting evaluation
    EVALUATED = "evaluated"    # Evaluation complete
    FOLLOW_UP = "follow_up"    # A follow-up was asked
    SKIPPED = "skipped"        # Question skipped (time/choice)


class InterviewTurn(BaseModel):
    """A single Q-A-eval triad. Immutable once evaluated."""
    turn_number: int  # 1-indexed within session
    question: Question
    answer_text: Optional[str] = None
    answer_audio_url: Optional[str] = None  # Future: voice mode
    answer_started_at: Optional[datetime] = None
    answer_submitted_at: Optional[datetime] = None
    status: TurnStatus = TurnStatus.PENDING
    evaluation: Optional["AnswerEvaluation"] = None  # Populated by Module 3
    follow_up_turns: List["InterviewTurn"] = Field(
        default_factory=list,
        description="Nested follow-ups (tree structure, usually depth ≤ 2)"
    )


class SessionStatus(str, Enum):
    CREATED = "created"
    IN_PROGRESS = "in_progress"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class InterviewSession(BaseModel):
    """Top-level LangGraph state object. Persisted to Postgres after every turn."""
    session_id: str = Field(..., description="UUIDv4")
    candidate_id: str
    job_id: str
    skill_gap_report_id: str  # FK to the report that seeded this session
    status: SessionStatus
    current_turn_number: int = 0
    turns: List[InterviewTurn] = Field(default_factory=list)
    question_set: QuestionSet  # May be mutated (reordering, injection)
    session_started_at: datetime
    session_ended_at: Optional[datetime] = None
    config: dict = Field(
        default_factory=lambda: {"max_turns": 12, "allow_follow_ups": True}
    )

    @property
    def completed_turns(self) -> List[InterviewTurn]:
        return [t for t in self.turns if t.status == TurnStatus.EVALUATED]
```

### 2.4 Per-Answer Evaluation (Output of Module 3, Input back to Module 2)

```python
class ScoreDimension(str, Enum):
    ACCURACY = "accuracy"        # Factually correct?
    DEPTH = "depth"              # Nuanced understanding?
    CLARITY = "clarity"          # Well-structured communication?
    RELEVANCE = "relevance"      # Addresses the question asked?
    CONFIDENCE = "confidence"    # Tone / delivery (text proxy)


class DimensionScore(BaseModel):
    dimension: ScoreDimension
    score: float = Field(..., ge=0.0, le=10.0)
    rationale: str = Field(..., max_length=500)


class AnswerEvaluation(BaseModel):
    """The atomic evaluation returned by Module 3 for a single answer.

    This is **Handoff #3**. Interview Agent uses this to decide:
    - Whether to ask a follow-up
    - Which question to ask next (adaptive routing)
    - When to end the session
    """
    evaluation_id: str = Field(..., description="UUIDv4")
    session_id: str
    turn_number: int
    candidate_id: str
    evaluated_at: datetime

    # Scoring
    dimension_scores: List[DimensionScore]
    overall_score: float = Field(..., ge=0.0, le=10.0)
    weighted_score: float = Field(
        ..., ge=0.0, le=10.0,
        description="Overall score weighted by question difficulty + gap severity"
    )

    # Qualitative
    summary_feedback: str = Field(
        ..., max_length=2000,
        description="2-4 paragraphs of actionable feedback"
    )
    strengths: List[str] = Field(default_factory=list, max_length=5)
    improvements: List[str] = Field(default_factory=list, max_length=5)
    model_answer_snippet: Optional[str] = Field(
        None, description="A concise exemplar answer for this question"
    )

    # Routing hints for the Interview Agent (LangGraph conditional edges)
    routing_hint: str = Field(
        ..., description="One of: 'next_question', 'follow_up', 'drill_deeper', 'skip_to_harder'"
    )
    suggested_follow_up: Optional[str] = Field(
        None, description="If routing_hint='follow_up', a suggested follow-up question text"
    )
    skill_level_inferred: Optional[ProficiencyLevel] = Field(
        None, description="Updated proficiency estimate based on this answer"
    )

    # Audit
    evaluator_version: str = Field(default="1.0.0")
    latency_ms: int = Field(..., description="Evaluation inference time")
```

### 2.5 Final Report (Output of Module 3, End-of-Session)

```python
class SkillProgression(BaseModel):
    skill_name: str
    initial_gap: ProficiencyLevel          # From SkillGapReport
    final_inferred_level: ProficiencyLevel
    progression_delta: int                 # Numeric change (-2 to +2)
    evidence_turns: List[int]              # Which turn numbers demonstrated this skill


class FinalReport(BaseModel):
    """Delivered to the candidate after session completion."""
    report_id: str
    session_id: str
    candidate_id: str
    job_id: str
    generated_at: datetime

    # Aggregates
    overall_score: float = Field(..., ge=0.0, le=10.0)
    percentile_estimate: Optional[float] = Field(None, ge=0.0, le=100.0)
    readiness_level: str = Field(..., description="e.g., 'ready', 'needs_work', 'not_ready'")

    # Breakdowns
    dimension_averages: dict[ScoreDimension, float]
    skill_progressions: List[SkillProgression]
    per_turn_evaluations: List[AnswerEvaluation]

    # Narrative
    executive_summary: str
    top_strengths: List[str]
    priority_gaps: List[str]
    study_plan: List[str] = Field(
        default_factory=list,
        description="Specific, ordered recommendations for closing gaps"
    )

    # Metadata
    total_session_duration_seconds: int
    total_turns: int
    report_version: str = "1.0.0"
```

---

## 3. Postgres Schema

### 3.1 Tables

```sql
-- Core entities
CREATE TABLE candidates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255),
    raw_description TEXT NOT NULL,
    parsed_requirements JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Module 1: Intake & Analysis
CREATE TABLE skill_gap_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    overall_match_score FLOAT CHECK (overall_match_score BETWEEN 0.0 AND 1.0),
    top_gaps JSONB NOT NULL DEFAULT '[]',
    strengths JSONB NOT NULL DEFAULT '[]',
    metadata JSONB DEFAULT '{}',
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Module 2: Interview Agent
CREATE TABLE interview_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
    job_id UUID REFERENCES jobs(id) ON DELETE CASCADE,
    skill_gap_report_id UUID REFERENCES skill_gap_reports(id),
    status VARCHAR(50) DEFAULT 'created' CHECK (status IN
        ('created','in_progress','paused','completed','abandoned')),
    question_set JSONB DEFAULT '{}',
    current_turn_number INT DEFAULT 0,
    config JSONB DEFAULT '{"max_turns": 12, "allow_follow_ups": true}',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ
);

CREATE TABLE interview_turns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES interview_sessions(id) ON DELETE CASCADE,
    turn_number INT NOT NULL,
    question JSONB NOT NULL,
    answer_text TEXT,
    answer_started_at TIMESTAMPTZ,
    answer_submitted_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'pending',
    evaluation JSONB,  -- Nullable until Module 3 writes it
    parent_turn_id UUID REFERENCES interview_turns(id),  -- For follow-up tree
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, turn_number)
);

-- Module 3: Evaluation & Reporting
CREATE TABLE answer_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    turn_id UUID REFERENCES interview_turns(id) ON DELETE CASCADE,
    session_id UUID REFERENCES interview_sessions(id) ON DELETE CASCADE,
    dimension_scores JSONB NOT NULL,
    overall_score FLOAT CHECK (overall_score BETWEEN 0.0 AND 10.0),
    weighted_score FLOAT CHECK (weighted_score BETWEEN 0.0 AND 10.0),
    summary_feedback TEXT,
    strengths JSONB DEFAULT '[]',
    improvements JSONB DEFAULT '[]',
    routing_hint VARCHAR(50) NOT NULL,
    suggested_follow_up TEXT,
    skill_level_inferred VARCHAR(50),
    evaluator_version VARCHAR(50) DEFAULT '1.0.0',
    latency_ms INT,
    evaluated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE final_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES interview_sessions(id) ON DELETE CASCADE,
    overall_score FLOAT CHECK (overall_score BETWEEN 0.0 AND 10.0),
    readiness_level VARCHAR(50),
    dimension_averages JSONB DEFAULT '{}',
    skill_progressions JSONB DEFAULT '[]',
    executive_summary TEXT,
    top_strengths JSONB DEFAULT '[]',
    priority_gaps JSONB DEFAULT '[]',
    study_plan JSONB DEFAULT '[]',
    total_session_duration_seconds INT,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- pgvector: RAG document store (shared across modules)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(50) NOT NULL,  -- 'resume', 'jd', 'knowledge_base'
    source_id UUID NOT NULL,           -- candidate_id or job_id
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1536),            -- Adjust dimension to your model (OpenAI: 1536)
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_document_chunks_embedding ON document_chunks
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
```

### 3.2 Relationships

```
candidates 1───∞ skill_gap_reports
    │
    └─── interview_sessions 1───∞ interview_turns
              │
              └─── answer_evaluations

jobs 1───∞ skill_gap_reports
    └─── interview_sessions
    └─── document_chunks (source_type='jd')

candidates 1───∞ document_chunks (source_type='resume')

interview_sessions 1───1 final_reports
```

### 3.3 Data Flow

| Step | Table(s) | Actor |
|---|---|---|
| Upload resume | `candidates`, `document_chunks` | Module 1 |
| Upload JD | `jobs`, `document_chunks` | Module 1 |
| Generate gap report | `skill_gap_reports` | Module 1 |
| Start interview | `interview_sessions`, `interview_turns` | Module 2 |
| Submit answer | `interview_turns` (update) | Module 2 (WebSocket) |
| Evaluate answer | `answer_evaluations`, `interview_turns.evaluation` | Module 3 |
| Decide next step | `interview_turns` (insert follow-up) | Module 2 (LangGraph) |
| End session | `interview_sessions` (update), `final_reports` | Module 3 |

---

## 4. Repo / Folder Structure

```
ai-interview-prep/
├── README.md
├── ARCHITECTURE.md          <-- You are here
├── pyproject.toml           # Poetry / uv deps
├── .env.example
├── docker-compose.yml       # Postgres + pgvector, optional Redis
│
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI app factory, lifespan, routers
│   ├── config.py              # Pydantic-Settings, env vars
│   ├── dependencies.py        # Shared FastAPI dependencies (DB session, etc.)
│   │
│   ├── core/                  # Cross-cutting concerns (owned by both)
│   │   ├── __init__.py
│   │   ├── schemas.py         # ALL shared Pydantic models (§2)
│   │   ├── database.py        # SQLAlchemy engine, sessionmaker, Base
│   │   ├── models.py          # SQLAlchemy ORM models mirroring §3
│   │   ├── exceptions.py      # Custom HTTP + business exceptions
│   │   └── constants.py       # Enums, config defaults
│   │
│   ├── agents/                # Agent modules (the 3 modules)
│   │   ├── __init__.py
│   │   ├── intake/            # Module 1: Intake & Analysis (Person A)
│   │   │   ├── __init__.py
│   │   │   ├── router.py      # FastAPI routes: POST /intake/analyze
│   │   │   ├── service.py     # Business logic: parse, chunk, embed, gap analysis
│   │   │   ├── parser.py      # Resume parsers (PDF, DOCX)
│   │   │   ├── jd_parser.py   # JD normalizer
│   │   │   ├── gap_analyzer.py # LLM prompt + gap scoring logic
│   │   │   └── prompts.py     # Jinja2 / f-string prompts
│   │   │
│   │   ├── interview/         # Module 2: Interview Agent (Person B)
│   │   │   ├── __init__.py
│   │   │   ├── router.py      # FastAPI routes + WebSocket endpoint
│   │   │   ├── service.py     # Session orchestrator
│   │   │   ├── graph.py       # LangGraph state machine definition
│   │   │   ├── nodes.py       # LangGraph node implementations
│   │   │   ├── question_gen.py # RAG-based question generator
│   │   │   ├── websocket.py   # WebSocket manager (connection, broadcast)
│   │   │   └── prompts.py
│   │   │
│   │   └── evaluation/        # Module 3: Evaluation & Reporting (Person A)
│   │       ├── __init__.py
│   │       ├── router.py      # FastAPI routes: GET /reports/{id}
│   │       ├── service.py     # Final report assembler
│   │       ├── scorer.py      # Per-answer scoring engine (§5)
│   │       ├── report_writer.py # Narrative report generation
│   │       └── prompts.py
│   │
│   └── utils/
│       ├── __init__.py
│       ├── vector_store.py    # pgvector query helpers
│       └── llm_client.py      # Unified LLM wrapper (OpenAI, Anthropic, etc.)
│
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_intake.py
│   │   ├── test_interview.py
│   │   └── test_evaluation.py
│   └── integration/
│       └── test_full_flow.py
│
├── alembic/                   # Database migrations
│   └── versions/
│
└── scripts/
    ├── seed_knowledge_base.py # Pre-load domain chunks into pgvector
    └── migrate.sh
```

### 4.1 Import Rules

```
┌─────────────────────────────────────────────────────────────┐
│                  NO CIRCULAR IMPORTS ALLOWED                 │
│                                                                │
│  app.core.schemas          ←── imported by EVERY module      │
│                                                                │
│  app.agents.intake       ──►  app.core.schemas               │
│  app.agents.interview    ──►  app.core.schemas               │
│  app.agents.evaluation   ──►  app.core.schemas               │
│                                                                │
│  app.agents.interview    ──►  app.agents.evaluation.scorer   │
│                                (direct function call, §5)     │
│                                                                │
│  app.agents.intake       ──X──►  app.agents.interview        │
│  app.agents.evaluation   ──X──►  app.agents.interview        │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. Cross-Person Handoff: Evaluation Function Signature

### 5.1 The Contract

**File:** `app/agents/evaluation/scorer.py`
**Owner:** Person A (Module 3)
**Caller:** Person B (Module 2, inside LangGraph node)

```python
# app/agents/evaluation/scorer.py
from typing import Optional
from app.core.schemas import AnswerEvaluation, InterviewTurn, SkillGapReport


async def evaluate_answer(
    *,
    turn: InterviewTurn,
    skill_gap_report: SkillGapReport,
    session_history: list[InterviewTurn],
    job_description_text: str,
    candidate_resume_text: str,
    model: str = "gpt-4o",       # Overridable per call
    temperature: float = 0.2,
    timeout_seconds: int = 30,
) -> AnswerEvaluation:
    '''Evaluate a single answer within the full interview context.

    This function is called **synchronously within the LangGraph loop**
    (i.e., it is awaited by the Interview Agent's evaluation node).
    It must return within `timeout_seconds` or the Interview Agent will
    raise a timeout and degrade gracefully (retry or skip evaluation).

    Args:
        turn: The current turn containing the question + candidate answer.
            `turn.answer_text` must be non-null and non-empty.
        skill_gap_report: The original gap report for this session.
            Used to weight scoring by gap severity.
        session_history: All *previous* evaluated turns (excluding current).
            Used to detect contradictions, measure growth,
            and avoid repetitive feedback.
        job_description_text: Raw JD text (for grounding evaluation).
        candidate_resume_text: Raw resume text (for grounding evaluation).
        model: LLM model identifier passed to the unified LLM client.
        temperature: Sampling temperature for the evaluator LLM.
        timeout_seconds: Hard deadline. Person B's LangGraph node
            wraps this in `asyncio.wait_for`.

    Returns:
        AnswerEvaluation: Fully populated Pydantic model.

    Raises:
        EvaluationError: If the LLM returns unparseable output or
            if the answer is too short to evaluate meaningfully.
            The Interview Agent catches this and may ask
            the candidate to elaborate.
    '''
    ...  # Implementation owned by Person A
```

### 5.2 Usage in LangGraph (Person B's Code)

```python
# app/agents/interview/nodes.py
from app.agents.evaluation.scorer import evaluate_answer


async def evaluation_node(state: InterviewSession) -> InterviewSession:
    current_turn = state.turns[-1]

    # Fetch raw texts from DB (or cache)
    jd_text = await get_jd_text(state.job_id)
    resume_text = await get_resume_text(state.candidate_id)

    # Handoff: call Person A's function
    evaluation = await evaluate_answer(
        turn=current_turn,
        skill_gap_report=await get_gap_report(state.skill_gap_report_id),
        session_history=state.turns[:-1],  # Exclude current
        job_description_text=jd_text,
        candidate_resume_text=resume_text,
    )

    # Write back into state
    current_turn.evaluation = evaluation
    current_turn.status = TurnStatus.EVALUATED
    return state
```

### 5.3 Versioning & Breaking Changes

- **Patch changes** (bug fixes, prompt tuning): No signature change. Silent deploy.
- **Minor changes** (new optional fields): Add to `AnswerEvaluation`, default to `None`. Backward compatible.
- **Major changes** (new required args, model output shape changes): Require both persons to update. Use a `v2` suffix or bump `evaluator_version`.

**Rule:** If Person A needs to change this signature, they must open a PR and tag Person B for review. The CI integration test (`tests/integration/test_full_flow.py`) must pass before merge.

---

## 6. LangGraph State Machine (Reference for Person B)

Person A does not implement this, but must understand the data contract.

```
                        ┌─────────────┐
                        │    START    │
                        └──────┬──────┘
                               │ load skill_gap_report
                               ▼
                        ┌─────────────┐
                        │    INIT     │
                        │  question   │
                        │    set      │
                        └──────┬──────┘
                               │
                  ┌────────────┴────────────┐
                  ▼                         ▼
           ┌──────────────┐          ┌──────────────┐
           │    ASK_Q     │          │  FOLLOW_UP   │
           │  (WebSocket  │◄─────────│ (conditional │
           │    emit)     │          │    edge)     │
           └──────┬───────┘          └──────┬───────┘
                  │                         │
                  ▼                         │
           ┌──────────────┐                 │
           │  AWAIT_ANS   │─────────────────┘
           │  (WebSocket  │  candidate sends answer
           │   receive)   │
           └──────┬───────┘
                  │
                  ▼
           ┌──────────────┐
           │   EVALUATE   │───► calls evaluate_answer() (§5)
           │  (Person A   │     timeout: 30s
           │   function)  │
           └──────┬───────┘
                  │
                  ▼
           ┌──────────────┐
           │    ROUTE     │
           │ (conditional │
           │   edges)     │
           └──────┬───────┘
                  │
      ┌───────────┼───────────┬───────────┐
      ▼           ▼           ▼           ▼
   ┌──────┐   ┌──────┐    ┌──────┐    ┌──────┐
   │ next │   │follow│    │drill │    │ end  │
   │  _q  │   │ _up  │    │deeper│    │session│
   └──┬───┘   └──┬───┘    └──┬───┘    └──┬───┘
      │          │           │           │
      └──────────┴───────────┴───────────┘
                  │
                  ▼
           ┌─────────────┐
           │    END      │───► triggers final report generation
           └─────────────┘     (Module 3, async background task)
```

**Conditional edge logic** (Person B implements, Person A provides data):

| `routing_hint` | Action |
|---|---|
| `next_question` | Pop next question from `question_set` |
| `follow_up` | Inject `suggested_follow_up` as a new `InterviewTurn` with `parent_turn_id` |
| `drill_deeper` | Re-queue same question with higher difficulty |
| `skip_to_harder` | Skip remaining easy questions, jump to highest severity gap |

---

## 7. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| API Framework | FastAPI | HTTP + WebSocket endpoints |
| State Machine | LangGraph | Interview loop orchestration |
| Database | Postgres 15+ + pgvector | Relational data + embeddings |
| ORM | SQLAlchemy 2.0 (async) | Model mapping |
| Migrations | Alembic | Schema versioning |
| LLM Client | `openai` / `anthropic` via `app.utils.llm_client` | Unified wrapper |
| Vector Ops | pgvector + sqlalchemy-pgvector | RAG retrieval |
| Parser | pymupdf / python-docx | Resume text extraction |
| WebSocket | FastAPI native | Real-time interview |
| Background Jobs | celery or arq (future) | Final report generation |
| Testing | pytest + pytest-asyncio | Unit + integration |
| Packaging | poetry or uv | Dependency management |

---

## 8. Development Rules

1. **Single Source of Truth:** `app/core/schemas.py` is the only place for shared Pydantic models. No module redefines them.
2. **No Microservice RPC:** All inter-module calls are direct Python function calls within the same process. No HTTP between modules.
3. **DB as Checkpoint:** LangGraph state is persisted to `interview_sessions` + `interview_turns` after every node. A session can be resumed after a crash.
4. **Prompts Are Code:** Prompts live in `prompts.py` within each module, versioned with the module, and reviewed in PRs.
5. **Evaluations Are Blocking:** The interview waits for `evaluate_answer()`. Keep it under 30s. If it exceeds, degrade gracefully.
6. **pgvector for RAG Only:** `document_chunks` stores embeddings. All relational data lives in normalized tables.
7. **Test the Handoff:** `tests/integration/test_full_flow.py` exercises the full pipeline: upload → gap report → interview → evaluation → final report.

---

## 9. Glossary

| Term | Definition |
|---|---|
| Turn | One complete Question → Answer → Evaluation cycle |
| Follow-up | A nested turn spawned by the Interview Agent based on `routing_hint='follow_up'` |
| Gap Severity | 1-5 score computed from `(jd_required_level - resume_level) * jd_priority_weight` |
| Routing Hint | The evaluation's instruction to LangGraph on what to do next |
| Skill-Gap Report | The canonical artifact produced by Module 1 and consumed by Module 2 |

*End of ARCHITECTURE.md*