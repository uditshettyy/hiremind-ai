"""FastAPI routes for the Interview Agent (Module 2)."""

import os

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.interview.question_gen import build_question_set_from_gaps
from app.agents.interview.service import create_interview_session
from app.core.database import get_db
from app.core.schemas import QuestionSet, SkillGapReport

load_dotenv()

router = APIRouter(prefix="/interview", tags=["interview"])


class GenerateQuestionsRequest(BaseModel):
    """Request body for generating an interview question set."""

    skill_gap_report: SkillGapReport


async def get_openai_client() -> AsyncOpenAI:
    """Create the OpenAI client used by the existing RAG question generator."""

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured.",
        )

    return AsyncOpenAI(api_key=api_key)


@router.post(
    "/generate-questions",
    response_model=QuestionSet,
)
async def generate_questions(
    request: GenerateQuestionsRequest,
    db: AsyncSession = Depends(get_db),
    openai_client: AsyncOpenAI = Depends(get_openai_client),
) -> QuestionSet:
    """
    Generate a personalized interview QuestionSet and create its session.
    """

    try:
        question_set = await build_question_set_from_gaps(
            db=db,
            openai_client=openai_client,
            gap_report=request.skill_gap_report,
        )

        session = await create_interview_session(
            db=db,
            candidate_id=request.skill_gap_report.candidate_id,
            job_id=request.skill_gap_report.job_id,
            skill_gap_report_id=request.skill_gap_report.report_id,
            question_set=question_set,
        )

        question_set.session_id = session.session_id

        return question_set

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc