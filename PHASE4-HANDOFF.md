# PHASE 4: Evaluation & Reporting Agent — Implementation & Integration Guide

**Owner:** Person A (Module 3)  
**Status:** Completed & Tested (100% Pass Rate across Unit & Endpoint Tests)  
**Last Updated:** 2026-09-19  

---

## 1. Phase 4 Overview & Goals

Phase 4 implements **Module 3: Evaluation & Reporting Agent**, owned by Person A. It has two main responsibilities within the platform:

1. **Per-Answer Evaluation (`evaluate_answer`)**: Scores single Q&A turns mid-interview in real-time, providing atomic qualitative feedback, dimensional scores, inferred skill levels, and routing hints for Person B's Interview Agent state machine.
2. **Final Report Synthesis (`generate_final_report`)**: Aggregates all evaluated turns at session completion to produce a comprehensive candidate feedback report including readiness levels, dimension averages, skill progression deltas, strengths, priority gaps, and an actionable 4–8 step study plan.

---

## 2. How Phase 4 Connects to Previous & Future Phases

```
┌────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Modular Monolith                        │
│                                                                        │
│  ┌──────────────────────┐               ┌───────────────────────────┐  │
│  │       Module 1       │               │         Module 2          │  │
│  │  Intake & Analysis   │──(Handoff #1)▶│      Interview Agent      │  │
│  │      (Person A)      │               │        (Person B)         │  │
│  └──────────────────────┘               └─────────────┬─────────────┘  │
│             │                                         │                │
│             │ (SkillGapReport)                        │ (evaluate_     │
│             │                                         │  answer call)  │
│             ▼                                         ▼                │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                             Module 3                             │  │
│  │                   Evaluation & Reporting Agent                   │  │
│  │                            (Person A)                            │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│                   Shared Pydantic Models (schemas.py)                  │
└────────────────────────────────────────────────────────────────────────┘
```

### Connection to Phase 1 (Intake & Analysis Agent)
- **Shared Model `SkillGapReport`**: Module 1 outputs `SkillGapReport`. Phase 4 consumes this report to:
  - Weight answer scores by gap severity (harder gaps are weighted higher).
  - Compare claimed proficiency against inferred proficiency to compute `SkillProgression` deltas (`initial_gap` vs `final_inferred_level`).
  - Contextualize LLM evaluation prompts with resume/JD evidence quotes.

### Connection to Phase 3 (Interview Agent — Person B)
- **Direct Function Contract (`Handoff #2 / #3`)**:
  - Person B's LangGraph `evaluation_node` calls `evaluate_answer(...)` directly in-process.
  - Returns `AnswerEvaluation` containing `routing_hint` (`next_question`, `follow_up`, `drill_deeper`, `skip_to_harder`) and `suggested_follow_up`.
  - Person B's conditional edges evaluate `routing_hint` to decide whether to inject a follow-up, re-queue a question, or proceed to the next gap.
- **End-of-Session Trigger**:
  - When Person B's state machine hits the `END` node, `generate_final_report()` is triggered as a background task to compile the candidate's final report.

---

## 3. Codebase Structure & Implemented Files

```
app/
├── core/
│   ├── schemas.py              # ALL shared Pydantic models (Single Source of Truth)
│   ├── database.py             # Shared DB session engine with env fallback
│   └── exceptions.py           # Custom EvaluationError & ReportGenerationError
├── utils/
│   └── llm_client.py           # Unified LLM wrapper (Groq, OpenAI, Anthropic support)
├── agents/
│   └── evaluation/
│       ├── __init__.py
│       ├── scorer.py           # Pure per-answer scoring logic (§5.1 contract)
│       ├── report_writer.py    # End-of-session final report synthesis
│       ├── service.py          # Orchestration layer with optional DB persistence
│       ├── router.py           # FastAPI routes: POST /evaluate/answer, POST /report/generate
│       └── prompts.py          # System and user prompts for scorer & report writer
tests/
├── fixtures/
│   ├── sample_session.py       # Sample Q&A turns & SkillGapReport test fixtures
│   └── fake_llm.py             # Mock LLM implementations for deterministic testing
└── unit/
    └── test_evaluation.py      # Full unit & endpoint test suite
```

---

## 4. Function Contracts & API Specifications

### 4.1 Cross-Module Function Signature (Handoff Contract #2 & #3)
**File:** `app/agents/evaluation/scorer.py`  
**Caller:** Person B's LangGraph `evaluation_node`

```python
async def evaluate_answer(
    *,
    turn: InterviewTurn,
    skill_gap_report: SkillGapReport,
    session_history: list[InterviewTurn],
    job_description_text: str,
    candidate_resume_text: str,
    model: str | None = None,
    temperature: float = 0.2,
    timeout_seconds: int = 30,
) -> AnswerEvaluation
```

#### Evaluation Output Breakdown (`AnswerEvaluation`):
- `dimension_scores`: 5 dimensions rated 0.0–10.0 (`accuracy`, `depth`, `clarity`, `relevance`, `confidence`). Applied STAR framework for behavioral questions.
- `overall_score`: Unweighted mean score across the 5 dimensions.
- `weighted_score`: Adjusted score factoring in question difficulty and target skill gap severity.
- `routing_hint`: Instruction for LangGraph conditional edges (`next_question`, `follow_up`, `drill_deeper`, `skip_to_harder`).
- `suggested_follow_up`: Concrete follow-up text if the answer leaves something underexplored.
- `skill_level_inferred`: Updated `ProficiencyLevel` estimate for the target skill.

### 4.2 HTTP Endpoints

#### 1. `POST /evaluate/answer`
- **Request Body**: `EvaluateAnswerRequest` (`session_id`, `turn`, `skill_gap_report`, `session_history`, `job_description_text`, `candidate_resume_text`)
- **Response**: `AnswerEvaluation` (Status `200 OK`)

#### 2. `POST /report/generate`
- **Request Body**: `GenerateReportRequest` (`session_id`, `candidate_id`, `job_id`, `turns`, `skill_gap_report`, `total_session_duration_seconds`)
- **Response**: `FinalReport` (Status `200 OK`)

---

## 5. Verification & Testing

### Automated Test Suite (`tests/unit/test_evaluation.py`)
- **Strong Technical Answers**: Verifies high scores ($\ge 8.0$), correct skill inference, and forward routing hints (`next_question`, `skip_to_harder`).
- **Weak Behavioral Answers**: Verifies low scores ($< 5.0$), STAR framework gap flags in improvements, and `follow_up`/`drill_deeper` routing.
- **Short / Missing Answers**: Ensures `EvaluationError(reason="answer_too_short")` is raised without wasting LLM API calls.
- **Final Report Aggregation**: Verifies skill progression deltas, dimension averages, readiness classification (`ready`, `needs_work`, `not_ready`), and study plan generation.
- **HTTP Endpoint Integration**: Tests `POST /evaluate/answer` and `POST /report/generate` routes returning `200 OK`.

### Live Verification Status
- Running FastAPI server (`uvicorn app.main:app --reload`).
- Tested live requests via Swagger UI (`http://127.0.0.1:8000/docs`).
- **Result:** `POST /evaluate/answer` $\rightarrow$ `200 OK`, `POST /report/generate` $\rightarrow$ `200 OK`.

---

## 6. Phase 5 Connection & Integration Plan (Wiring Interview → Evaluation)

In **Phase 5**, Module 2 (Interview Agent) and Module 3 (Evaluation & Reporting Agent) are wired together in a joint integration session:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Phase 5 Wiring Flow                           │
│                                                                         │
│   Interview Agent (Module 2)               Evaluation Agent (Module 3)  │
│  ┌───────────────────────────┐            ┌──────────────────────────┐  │
│  │ LangGraph evaluation_node │───────────▶│ evaluate_answer()        │  │
│  │ (Swaps stub for real call)│            │ (scorer.py)              │  │
│  └───────────────────────────┘            └─────────────┬────────────┘  │
│                ▲                                        │               │
│                │                                        │               │
│                └───────────── AnswerEvaluation ─────────┘               │
│                        (with routing_hint & scores)                     │
│                                                                         │
│   LangGraph END Node                       report_writer.py             │
│  ┌───────────────────────────┐            ┌──────────────────────────┐  │
│  │ Session Completed         │───────────▶│ generate_final_report()  │  │
│  └───────────────────────────┘            └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 6.1 Swapping the Evaluation Stub
During Phase 3, Person B's LangGraph node (`evaluation_node` in `app/agents/interview/nodes.py`) uses a stubbed mock function. In Phase 5, this mock is swapped for the real `evaluate_answer()` function:

```python
from app.agents.evaluation.scorer import evaluate_answer

# Inside Person B's LangGraph evaluation node:
evaluation = await evaluate_answer(
    turn=current_turn,
    skill_gap_report=skill_gap_report,
    session_history=session_history,  # state.turns[:-1]
    job_description_text=job_description_text,
    candidate_resume_text=candidate_resume_text,
    model=None,  # Auto-resolves to provider default (llama-3.3-70b-versatile for Groq)
    temperature=0.2,
    timeout_seconds=30,
)
```

### 6.2 Contract Verification Checklist for Phase 5
1. **Input Types**:
   - `turn`: Valid `InterviewTurn` with non-empty `answer_text`.
   - `skill_gap_report`: `SkillGapReport` from Phase 1.
   - `session_history`: List of prior evaluated `InterviewTurn` items (`state.turns[:-1]`).
   - `job_description_text` & `candidate_resume_text`: Raw string content for LLM grounding.
2. **Output Handling**:
   - Returns `AnswerEvaluation` object.
   - Node updates `current_turn.evaluation = evaluation` and `current_turn.status = TurnStatus.EVALUATED`.
   - LangGraph conditional edge reads `evaluation.routing_hint` (`next_question`, `follow_up`, `drill_deeper`, `skip_to_harder`).
3. **Resilience & Graceful Degradation**:
   - `EvaluationError` is caught by Person B's evaluation node if `answer_text` is under 8 words or unparseable, enabling the agent to prompt the candidate to elaborate.
4. **End-of-Session Trigger**:
   - When the session reaches `SessionStatus.COMPLETED` (`END` node), `generate_final_report()` is invoked with `state.turns` to construct the final report.

---

## 7. Hand-off Readiness for Person B (Module 2)

Phase 4 is 100% complete, tested, and ready for Phase 5 integration:
1. No files inside `app/agents/interview/` were modified.
2. `app.core.schemas` contains all required Pydantic models.
3. Person B can import `from app.agents.evaluation.scorer import evaluate_answer` directly inside their LangGraph node once Phase 3 is ready.

