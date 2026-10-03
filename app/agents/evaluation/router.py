"""
app/agents/evaluation/router.py
Owner: Person A (Module 3)

Exposes the Evaluation & Reporting module's HTTP surface. Per ARCHITECTURE.md
§4.1 import rules, this module may only import app.core.schemas and its own
submodules — never app.agents.interview.

Note: Person B's LangGraph node calls `evaluate_answer()` (scorer.py) as a
direct in-process function call, NOT through this HTTP route. These routes
exist for: (a) manual/QA testing of the scoring and report logic in
isolation, and (b) any future out-of-process caller.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.exceptions import EvaluationError, ReportGenerationError
from app.core.schemas import AnswerEvaluation, FinalReport, InterviewTurn, SkillGapReport
from app.agents.evaluation.service import evaluate_and_persist, generate_and_persist_report

from app.utils.llm_client import generate_structured as _generate_structured


async def get_generate_structured():
    return _generate_structured


try:  # pragma: no cover - only used once app.dependencies exists in the real repo
    from app.dependencies import get_db  # type: ignore
except ImportError:
    async def get_db():  # falls back to None so routes stay importable/testable standalone
        yield None


router = APIRouter(tags=["evaluation"])


# ---------------------------------------------------------------------------
# Request bodies (route-local; NOT shared models — the shared handoff models
# live in app.core.schemas per Development Rule #1)
# ---------------------------------------------------------------------------

class EvaluateAnswerRequest(BaseModel):
    session_id: str
    turn: InterviewTurn
    skill_gap_report: SkillGapReport
    session_history: list[InterviewTurn] = Field(default_factory=list)
    job_description_text: str
    candidate_resume_text: str
    model: Optional[str] = None
    temperature: float = 0.2
    timeout_seconds: int = 30


class GenerateReportRequest(BaseModel):
    session_id: str
    candidate_id: str
    job_id: str
    turns: list[InterviewTurn]
    skill_gap_report: SkillGapReport
    total_session_duration_seconds: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/evaluate/answer", response_model=AnswerEvaluation)
async def evaluate_answer_route(
    payload: EvaluateAnswerRequest,
    db=Depends(get_db),
    generate_structured=Depends(get_generate_structured),
) -> AnswerEvaluation:
    try:
        return await evaluate_and_persist(
            db=db,
            turn=payload.turn,
            skill_gap_report=payload.skill_gap_report,
            session_id=payload.session_id,
            session_history=payload.session_history,
            job_description_text=payload.job_description_text,
            candidate_resume_text=payload.candidate_resume_text,
            model=payload.model,
            temperature=payload.temperature,
            timeout_seconds=payload.timeout_seconds,
            _generate_structured=generate_structured,
        )
    except EvaluationError as exc:
        # 422: the request was well-formed but the answer couldn't be scored
        # (too short / unparseable LLM output / timeout) — matches the
        # "Interview Agent catches this and may ask candidate to elaborate"
        # contract in ARCHITECTURE.md §5.1, translated to an HTTP-caller shape.
        raise HTTPException(
            status_code=422,
            detail={"reason": exc.reason, "message": str(exc)},
        ) from exc


@router.post("/report/generate", response_model=FinalReport)
async def generate_report_route(
    payload: GenerateReportRequest,
    db=Depends(get_db),
    generate_structured=Depends(get_generate_structured),
) -> FinalReport:
    try:
        return await generate_and_persist_report(
            db=db,
            session_id=payload.session_id,
            candidate_id=payload.candidate_id,
            job_id=payload.job_id,
            turns=payload.turns,
            skill_gap_report=payload.skill_gap_report,
            total_session_duration_seconds=payload.total_session_duration_seconds,
            _generate_structured=generate_structured,
        )
    except ReportGenerationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


EvaluateAnswerRequest.model_rebuild()
GenerateReportRequest.model_rebuild()


