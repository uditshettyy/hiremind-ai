"""WebSocket interface for the Interview Agent."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agents.interview.nodes import (
    InterviewGraphState,
    ask_question,
    await_answer,
    evaluate_turn,
    handle_follow_up,
    move_to_next_question,
    route_after_evaluation,
)
from app.core.database import AsyncSessionLocal
from app.core.models import SkillGapReportORM
from app.core.schemas import (
    SkillGapReport,
      SessionStatus,
       InterviewTurn,
    TurnStatus,
)
from app.agents.interview.service import (
    get_interview_session,
    persist_interview_turn,
    update_interview_session,
)

router = APIRouter()


@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(
    websocket: WebSocket,
    session_id: str,
):
    await websocket.accept()

    try:
        async with AsyncSessionLocal() as db:
            # ---------------------------------------------------------
            # 1. Load the persisted interview session.
            # ---------------------------------------------------------
            session = await get_interview_session(
                db,
                session_id=session_id,
            )
            
            if session is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Interview session not found.",
                    }
                )
                await websocket.close(code=1008)
                return
            session = session.model_copy(
            update={"status": SessionStatus.IN_PROGRESS}
            )

            await update_interview_session(
            db,
            session=session,
            )

            # ---------------------------------------------------------
            # 2. Load the SkillGapReport.
            # ---------------------------------------------------------
            if session.skill_gap_report_id is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "SkillGapReport is missing for this session.",
                    }
                )
                await websocket.close(code=1008)
                return

            result = await db.execute(
                select(SkillGapReportORM).where(
                    SkillGapReportORM.id == session.skill_gap_report_id
                )
            )

            report_orm = result.scalar_one_or_none()

            if report_orm is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "SkillGapReport not found.",
                    }
                )
                await websocket.close(code=1008)
                return

            skill_gap_report = SkillGapReport(
                report_id=str(report_orm.id),
                candidate_id=str(report_orm.candidate_id),
                job_id=str(report_orm.job_id),
                generated_at=report_orm.generated_at,
                overall_match_score=report_orm.overall_match_score,
                top_gaps=report_orm.top_gaps,
                strengths=report_orm.strengths,
                metadata=report_orm.metadata_,
            )

            # ---------------------------------------------------------
            # 3. Validate the QuestionSet.
            # ---------------------------------------------------------
            if session.question_set is None:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "QuestionSet is missing for this session.",
                    }
                )
                await websocket.close(code=1008)
                return

            if not session.question_set.questions:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "QuestionSet contains no questions.",
                    }
                )
                await websocket.close(code=1008)
                return

            # ---------------------------------------------------------
            # 4. Build the Interview Agent state.
            # ---------------------------------------------------------
            state: InterviewGraphState = {
                "session": session,
                "skill_gap_report": skill_gap_report,
                "job_description_text": "",
                "candidate_resume_text": "",
                "db": db,
                "openai_client": None,
                "answer_text": None,
            }

            # ---------------------------------------------------------
            # 5. Create the first InterviewTurn.
            # ---------------------------------------------------------
            state = await ask_question(state)

            await websocket.send_json(
                {
                    "type": "connected",
                    "session_id": session.session_id,
                    "status": session.status.value,
                }
            )

            # ---------------------------------------------------------
            # 6. Interview loop.
            #
            #    Question
            #       ↓
            #    Answer
            #       ↓
            #    Evaluation
            #       ↓
            #    Routing
            #       ↓
            #    Next question / Follow-up
            # ---------------------------------------------------------
            while True:
                session = state["session"]

                current_turn = session.turns[-1]

                # -----------------------------------------------------
                # Send the current question.
                # -----------------------------------------------------
                await websocket.send_json(
                    {
                        "type": "question",
                        "turn_number": current_turn.turn_number,
                        "question": current_turn.question.model_dump(
                            mode="json"
                        ),
                    }
                )

                # -----------------------------------------------------
                # Wait for the candidate's answer.
                # -----------------------------------------------------
                message = await websocket.receive_json()

                if message.get("type") != "answer":
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "Expected an answer message.",
                        }
                    )
                    continue

                answer_text = message.get("answer_text")

                if not isinstance(answer_text, str) or not answer_text.strip():
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "answer_text must be a non-empty string.",
                        }
                    )
                    continue

                # -----------------------------------------------------
                # Attach the answer to the current InterviewTurn.
                # -----------------------------------------------------
                state["answer_text"] = answer_text

                state = await await_answer(state)

                # -----------------------------------------------------
                # Evaluate the answer.
                # -----------------------------------------------------
                state = await evaluate_turn(state)
                await persist_interview_turn(
                    db,
                session=state["session"],
                turn=state["session"].turns[-1],
                )
                session = state["session"]
                evaluated_turn = session.turns[-1]

                evaluation = evaluated_turn.evaluation

                await websocket.send_json(
                    {
                        "type": "evaluation",
                        "turn_number": evaluated_turn.turn_number,
                        "evaluation": (
                            evaluation.model_dump(mode="json")
                            if evaluation is not None
                            else None
                        ),
                    }
                )

                # -----------------------------------------------------
                # Decide what happens next.
                # -----------------------------------------------------
                route = route_after_evaluation(state)

                if route == "next_question":
                    state = move_to_next_question(state)
                    if state["session"].status == SessionStatus.COMPLETED:
                        await update_interview_session(
                            db,
                            session=state["session"],
                        )

                        await websocket.send_json(
                            {
                                "type": "completed",
                                "session_id": state["session"].session_id,
                                "status": state["session"].status.value,
                            }
                        )

                        await websocket.close()
                        return

                elif route == "follow_up":
                    state = handle_follow_up(state)

                else:
                    # Phase 3 explicitly handles next question and
                    # follow-up. Other architecture routes are not
                    # implemented in this WebSocket scope.
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                f"Unsupported routing hint for Phase 3: "
                                f"{route}"
                            ),
                        }
                    )
                    return

                # -----------------------------------------------------
                # Check whether the interview has been exhausted.
                # -----------------------------------------------------

    except WebSocketDisconnect:
        return

    except Exception as exc:
        await websocket.send_json(
            {
                "type": "error",
                "message": str(exc),
            }
        )
        await websocket.close(code=1011)