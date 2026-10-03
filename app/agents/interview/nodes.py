"""
Interview Agent LangGraph nodes.

Phase 3 implementation based on ARCHITECTURE.md.
"""

import os
from typing import TypedDict
import asyncio
from app.agents.interview.evaluation_mock import evaluate_answer
from app.core.schemas import AnswerEvaluation
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from app.core.schemas import (
    InterviewSession,
    InterviewTurn,
    SkillGapReport,
    TurnStatus,
    SessionStatus,
)


class InterviewGraphState(TypedDict, total=False):
    """
    State passed between Interview Agent LangGraph nodes.
    """

    session: InterviewSession
    skill_gap_report: SkillGapReport
    job_description_text: str
    candidate_resume_text: str

    # Runtime dependencies.
    db: AsyncSession
    openai_client: AsyncOpenAI
    answer_text: str

async def load_skill_gap(
    state: InterviewGraphState,
) -> InterviewGraphState:
    """
    Load the SkillGapReport required by the Interview Agent.

    Module 1 -> Module 2 handoff is SkillGapReport.
    """

    skill_gap_report = state.get("skill_gap_report")

    if skill_gap_report is None:
        raise ValueError(
            "SkillGapReport is required for the interview session."
        )

    return {
        **state,
        "skill_gap_report": skill_gap_report,
    }


async def init_question_set(
    state: InterviewGraphState,
) -> InterviewGraphState:
    """
    Generate the initial QuestionSet from the SkillGapReport.
    """
    
    skill_gap_report = state.get("skill_gap_report")

    if skill_gap_report is None:
        raise ValueError(
            "SkillGapReport must be loaded before initializing questions."
        )

    session = state.get("session")

    if session is None:
        raise ValueError(
            "InterviewSession is required before initializing questions."
        )

    db = state.get("db")

    if db is None:
        raise ValueError(
            "Database session is required for question generation."
        )

    openai_client = state.get("openai_client")

    if openai_client is None:
        raise ValueError(
            "OpenAI client is required for question generation."
        )

    from app.agents.interview.question_gen import (
        build_question_set_from_gaps,
    )

    question_set = await build_question_set_from_gaps(
        db=db,
        openai_client=openai_client,
        gap_report=skill_gap_report,
    )

    return {
        **state,
        "session": session.model_copy(
            update={
                "question_set": question_set,
            }
        ),
    }
async def ask_question(
    state: InterviewGraphState,
) -> InterviewGraphState:
    """
    Prepare the current interview question.

    The WebSocket layer will emit the question to the client later.
    """

    session = state.get("session")

    if session is None:
        raise ValueError(
            "InterviewSession is required before asking a question."
        )

    question_set = session.question_set

    if session.current_turn_number >= len(question_set.questions):
        raise ValueError(
            "No more questions are available in the QuestionSet."
        )

    question = question_set.questions[session.current_turn_number]

    turn = InterviewTurn(
        turn_number=session.current_turn_number + 1,
        question=question,
        status=TurnStatus.PENDING,
    )

    updated_session = session.model_copy(
        update={
            "current_turn_number": session.current_turn_number + 1,
            "turns": [*session.turns, turn],
        }
    )

    return {
        **state,
        "session": updated_session,
    }

async def await_answer(
    state: InterviewGraphState,
) -> InterviewGraphState:
    """
    Process the candidate's submitted answer.

    The WebSocket layer will provide the answer text.
    This node attaches it to the current InterviewTurn.
    """

    session = state.get("session")

    if session is None:
        raise ValueError(
            "InterviewSession is required before processing an answer."
        )

    if not session.turns:
        raise ValueError(
            "There is no interview turn waiting for an answer."
        )

    answer_text = state.get("answer_text")

    if not answer_text:
        raise ValueError(
            "Candidate answer is required."
        )

    current_turn = session.turns[-1]

    updated_turn = current_turn.model_copy(
        update={
            "answer_text": answer_text,
            "answer_submitted_at": datetime.now(timezone.utc),
            "status": TurnStatus.ANSWERED,
        }
    )

    updated_turns = [
        *session.turns[:-1],
        updated_turn,
    ]

    updated_session = session.model_copy(
        update={
            "turns": updated_turns,
        }
    )

    return {
        **state,
        "session": updated_session,
    }
async def evaluate_turn(
    state: InterviewGraphState,
) -> InterviewGraphState:
    """
    Evaluate the candidate's current interview answer.
    """

    session = state.get("session")

    if session is None:
        raise ValueError(
            "InterviewSession is required before evaluating an answer."
        )

    if not session.turns:
        raise ValueError(
            "There is no interview turn available for evaluation."
        )

    skill_gap_report = state.get("skill_gap_report")

    if skill_gap_report is None:
        raise ValueError(
            "SkillGapReport is required for answer evaluation."
        )

    current_turn = session.turns[-1]

    if current_turn.status != TurnStatus.ANSWERED:
        raise ValueError(
            "Current interview turn must be ANSWERED before evaluation."
        )

    evaluation = await asyncio.wait_for(
        evaluate_answer(
            turn=current_turn,
            skill_gap_report=skill_gap_report,
            session_history=session.turns[:-1],
            job_description_text=state.get(
                "job_description_text",
                "",
            ),
            candidate_resume_text=state.get(
                "candidate_resume_text",
                "",
            ),
        ),
        timeout=30,
    )

    updated_turn = current_turn.model_copy(
        update={
            "evaluation": evaluation,
            "status": TurnStatus.EVALUATED,
        }
    )

    updated_session = session.model_copy(
        update={
            "turns": [
                *session.turns[:-1],
                updated_turn,
            ],
        }
    )

    return {
        **state,
        "session": updated_session,
    }
def route_after_evaluation(
    state: InterviewGraphState,
) -> str:
    """
    Decide what the Interview Agent should do after evaluation.
    """

    session = state.get("session")

    if session is None:
        raise ValueError(
            "InterviewSession is required for routing."
        )

    if not session.turns:
        raise ValueError(
            "There is no interview turn available for routing."
        )

    current_turn = session.turns[-1]

    if current_turn.evaluation is None:
        raise ValueError(
            "Current turn must have an evaluation before routing."
        )

    routing_hint = current_turn.evaluation.routing_hint

    allowed_routes = {
        "next_question",
        "follow_up",
        "drill_deeper",
        "skip_to_harder",
    }

    if routing_hint not in allowed_routes:
        raise ValueError(
            f"Unknown routing hint: {routing_hint}"
        )

    return routing_hint
def move_to_next_question(
    state: InterviewGraphState,
) -> InterviewGraphState:
    """
    Move the interview to the next question in the QuestionSet.
    """

    session = state.get("session")

    if session is None:
        raise ValueError(
            "InterviewSession is required."
        )

    question_set = session.question_set

    if session.current_turn_number >= len(question_set.questions):
        return {
            **state,
            "session": session.model_copy(
                update={
                    "status": SessionStatus.COMPLETED,
                }
            ),
        }

    question = question_set.questions[session.current_turn_number]

    turn = InterviewTurn(
        turn_number=session.current_turn_number + 1,
        question=question,
        status=TurnStatus.PENDING,
    )

    updated_session = session.model_copy(
        update={
            "current_turn_number": session.current_turn_number + 1,
            "turns": [
                *session.turns,
                turn,
            ],
        }
    )

    return {
        **state,
        "session": updated_session,
    }
def handle_follow_up(state: InterviewGraphState) -> InterviewGraphState:
    session = state.get("session")

    if session is None:
        raise ValueError("InterviewSession is required.")

    if not session.turns:
        raise ValueError("No interview turns available.")

    latest_turn = session.turns[-1]

    if latest_turn.evaluation is None:
        raise ValueError("Latest turn must have an evaluation.")

    follow_up_question = latest_turn.evaluation.suggested_follow_up

    if not follow_up_question:
        raise ValueError("Evaluation does not contain a suggested follow-up question.")

    follow_up_turn = InterviewTurn(
        turn_number=session.current_turn_number + 1,
        question=latest_turn.question.model_copy(
            update={
                "question_id": f"{latest_turn.question.question_id}-followup",
                "question_text": follow_up_question,
                "question_type": "follow_up",
            }
        ),
        status=TurnStatus.PENDING,
    )

    updated_session = session.model_copy(
        update={
            "current_turn_number": session.current_turn_number + 1,
            "turns": [*session.turns, follow_up_turn],
        }
    )

    return {
        **state,
        "session": updated_session,
    }
def handle_drill_deeper(state: InterviewGraphState) -> InterviewGraphState:
    session = state.get("session")

    if session is None:
        raise ValueError("InterviewSession is required.")

    if not session.turns:
        raise ValueError("No interview turns available.")

    latest_turn = session.turns[-1]

    current_difficulty = latest_turn.question.difficulty

    difficulty_order = {
        "easy": "medium",
        "medium": "hard",
        "hard": "hard",
    }

    next_difficulty = difficulty_order[current_difficulty.value]

    deeper_question = latest_turn.question.model_copy(
        update={
            "question_id": f"{latest_turn.question.question_id}-deeper",
            "difficulty": next_difficulty,
        }
    )

    deeper_turn = InterviewTurn(
        turn_number=session.current_turn_number + 1,
        question=deeper_question,
        status=TurnStatus.PENDING,
    )

    updated_session = session.model_copy(
        update={
            "current_turn_number": session.current_turn_number + 1,
            "turns": [*session.turns, deeper_turn],
        }
    )

    return {
        **state,
        "session": updated_session,
    }