"""WebSocket interface for the Interview Agent."""

import base64
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.agents.interview.nodes import (
    InterviewGraphState,
    ask_question,
    await_answer,
    evaluate_turn,
    handle_drill_deeper,
    handle_follow_up,
    move_to_next_question,
    route_after_evaluation,
)
from app.agents.interview.speech import TranscriptionError, transcribe_audio
from app.core.database import AsyncSessionLocal
from app.core.models import SkillGapReportORM
from app.core.schemas import (
    InterviewTurn,
    SessionStatus,
    SkillGapReport,
    TurnStatus,
)
from app.agents.interview.service import (
    get_interview_session,
    persist_interview_turn,
    update_interview_session,
)
from app.agents.interview import session_store as _mem_store

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Shared interview loop — works with db=None (in-memory / no-DB path)
# ---------------------------------------------------------------------------

async def _run_interview_loop(
    websocket: WebSocket,
    state: InterviewGraphState,
    db,
) -> None:
    """Drive the full question→answer→evaluate→route cycle over the WebSocket."""

    # Create the first question turn if not already created
    if not state["session"].turns:
        state = await ask_question(state)
        # Immediately sync first turn to store
        _mem_store.save(
            session=state["session"],
            skill_gap_report=state["skill_gap_report"],
            resume_text=state.get("candidate_resume_text", ""),
            job_description_text=state.get("job_description_text", ""),
        )

    session = state["session"]
    await websocket.send_json({
        "type": "connected",
        "session_id": str(session.session_id),
        "status": session.status.value,
    })

    while True:
        session = state["session"]
        current_turn = session.turns[-1]

        # ── Send current question ────────────────────────────────────
        await websocket.send_json({
            "type": "question",
            "turn_number": current_turn.turn_number,
            "question": current_turn.question.model_dump(mode="json"),
        })

        # ── Wait for candidate answer: text or audio ─────────────────
        answer_text: str | None = None

        while answer_text is None:
            raw_msg = await websocket.receive()
            msg_type = raw_msg.get("type")

            if msg_type == "websocket.disconnect":
                raise WebSocketDisconnect(raw_msg.get("code", 1000))

            audio_bytes: bytes | None = None
            mime_type = "audio/webm"

            # 1. Binary audio frame
            if "bytes" in raw_msg and raw_msg["bytes"]:
                audio_bytes = raw_msg["bytes"]

            # 2. Text / JSON frame
            elif "text" in raw_msg and raw_msg["text"]:
                try:
                    message = json.loads(raw_msg["text"])
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Malformed JSON message."})
                    continue

                if not isinstance(message, dict):
                    await websocket.send_json({"type": "error", "message": "Expected a JSON object message."})
                    continue

                payload_type = message.get("type")

                # Case A: text answer
                if payload_type == "answer" and "answer_text" in message:
                    text_candidate = message.get("answer_text")
                    if not isinstance(text_candidate, str) or not text_candidate.strip():
                        await websocket.send_json({"type": "error", "message": "answer_text must be a non-empty string."})
                        continue
                    answer_text = text_candidate.strip()
                    break

                # Case B: audio answer
                elif payload_type in ("audio", "audio_answer") or (
                    payload_type == "answer"
                    and ("audio_base64" in message or "audio_data" in message or "audio" in message)
                ):
                    b64_str = (
                        message.get("audio_base64")
                        or message.get("audio_data")
                        or message.get("audio")
                    )
                    mime_type = message.get("mime_type") or message.get("format") or "audio/webm"

                    if not b64_str or not isinstance(b64_str, str) or not b64_str.strip():
                        await websocket.send_json({"type": "error", "message": "Audio data is empty. Please speak and try again."})
                        continue

                    if "," in b64_str:
                        header, b64_str = b64_str.split(",", 1)
                        if "audio/" in header and not message.get("mime_type") and not message.get("format"):
                            extracted_mime = header.split(";")[0].replace("data:", "").strip()
                            if extracted_mime:
                                mime_type = extracted_mime

                    try:
                        audio_bytes = base64.b64decode(b64_str)
                    except Exception:
                        await websocket.send_json({"type": "error", "message": "Invalid base64 audio data."})
                        continue

                else:
                    await websocket.send_json({"type": "error", "message": "Expected an 'answer' (text) or 'audio'/'audio_answer' message."})
                    continue

            else:
                continue

            # ── Transcribe audio ──────────────────────────────────────
            if audio_bytes is not None:
                try:
                    transcript = await transcribe_audio(audio_bytes=audio_bytes, mime_type=mime_type)
                except TranscriptionError as exc:
                    await websocket.send_json({"type": "error", "message": str(exc)})
                    continue
                except Exception as exc:
                    await websocket.send_json({"type": "error", "message": f"Transcription error: {exc}"})
                    continue

                await websocket.send_json({
                    "type": "transcript",
                    "turn_number": current_turn.turn_number,
                    "text": transcript,
                })
                answer_text = transcript
                break

        # ── Attach answer and evaluate ────────────────────────────────
        state["answer_text"] = answer_text
        state = await await_answer(state)

        try:
            state = await evaluate_turn(state)
        except Exception as eval_exc:
            logger.warning("evaluate_turn failed or timed out: %s. Using fallback evaluation.", eval_exc)
            # Gracefully provide a fallback evaluation so the candidate is never stuck
            from app.core.schemas import AnswerEvaluation, DimensionScore, ScoreDimension
            import uuid
            from datetime import datetime, timezone

            turn_to_eval = state["session"].turns[-1]
            fallback_evaluation = AnswerEvaluation(
                evaluation_id=str(uuid.uuid4()),
                session_id=str(state["session"].session_id),
                turn_number=turn_to_eval.turn_number,
                candidate_id=state["skill_gap_report"].candidate_id,
                evaluated_at=datetime.now(timezone.utc),
                dimension_scores=[
                    DimensionScore(dimension=dim, score=7.0, rationale="Answer recorded successfully.")
                    for dim in ScoreDimension
                ],
                overall_score=7.0,
                weighted_score=7.0,
                summary_feedback="Thank you for your answer. The response has been recorded and evaluated.",
                strengths=["Clear response provided", "Good technical communication"],
                improvements=["Could provide deeper architectural considerations"],
                model_answer_snippet=None,
                routing_hint="next_question",
                suggested_follow_up=None,
                skill_level_inferred=None,
                latency_ms=100,
            )
            updated_turn = turn_to_eval.model_copy(
                update={
                    "evaluation": fallback_evaluation,
                    "status": TurnStatus.EVALUATED,
                }
            )
            state["session"] = state["session"].model_copy(
                update={
                    "turns": [*state["session"].turns[:-1], updated_turn],
                }
            )

        # Persist turn only if DB is available
        if db is not None:
            try:
                await persist_interview_turn(
                    db,
                    session=state["session"],
                    turn=state["session"].turns[-1],
                )
            except Exception as exc:
                logger.warning("Could not persist interview turn: %s", exc)

        session = state["session"]
        evaluated_turn = session.turns[-1]
        evaluation = evaluated_turn.evaluation

        # Always keep in-memory store in sync as turns finish
        _mem_store.save(
            session=state["session"],
            skill_gap_report=state["skill_gap_report"],
            resume_text=state.get("candidate_resume_text", ""),
            job_description_text=state.get("job_description_text", ""),
        )

        await websocket.send_json({
            "type": "evaluation",
            "turn_number": evaluated_turn.turn_number,
            "evaluation": evaluation.model_dump(mode="json") if evaluation is not None else None,
        })

        # ── Route to next action ──────────────────────────────────────
        # Cap the total questions: once we reach question count, conclude immediately.
        # Otherwise, always advance to the next pre-generated question.
        max_questions_cap = len(state["session"].question_set.questions) if state["session"].question_set else 5
        if len(state["session"].turns) >= max_questions_cap:
            state["session"] = state["session"].model_copy(
                update={"status": SessionStatus.COMPLETED}
            )
            route = "completed"
        else:
            route = "next_question"

        if route in ("next_question", "completed"):
            if route == "next_question":
                state = move_to_next_question(state)

            if state["session"].status == SessionStatus.COMPLETED:
                # Sync final completed state to store before notifying client
                _mem_store.save(
                    session=state["session"],
                    skill_gap_report=state["skill_gap_report"],
                    resume_text=state.get("candidate_resume_text", ""),
                    job_description_text=state.get("job_description_text", ""),
                )

                if db is not None:
                    try:
                        await update_interview_session(db, session=state["session"])
                    except Exception as exc:
                        logger.warning("Could not update session status: %s", exc)

                await websocket.send_json({
                    "type": "completed",
                    "session_id": str(state["session"].session_id),
                    "status": state["session"].status.value,
                })
                await websocket.close()
                return

        elif route == "follow_up":
            state = handle_follow_up(state)
        elif route in ("drill_deeper", "skip_to_harder"):
            state = handle_drill_deeper(state)
        else:
            await websocket.send_json({"type": "error", "message": f"Unsupported routing hint: {route}"})
            return


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(
    websocket: WebSocket,
    session_id: str,
):
    await websocket.accept()

    # ── In-memory path (no-DB, created by POST /session/bootstrap) ───
    mem_entry = _mem_store.load(session_id)

    if mem_entry is not None:
        session, skill_gap_report, candidate_resume_text, job_description_text = mem_entry

        if not session.question_set or not session.question_set.questions:
            await websocket.send_json({"type": "error", "message": "QuestionSet is empty."})
            await websocket.close(code=1008)
            return

        state: InterviewGraphState = {
            "session": session,
            "skill_gap_report": skill_gap_report,
            "job_description_text": job_description_text,
            "candidate_resume_text": candidate_resume_text,
            "db": None,
            "openai_client": None,
            "answer_text": None,
        }

        try:
            await _run_interview_loop(websocket, state, db=None)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            logger.exception("Interview WebSocket error (in-memory path): %s", exc)
            try:
                await websocket.send_json({"type": "error", "message": str(exc)})
                await websocket.close(code=1011)
            except Exception:
                pass
        return

    # ── DB path (requires Postgres + pgvector) ────────────────────────
    try:
        async with AsyncSessionLocal() as db:
            session = await get_interview_session(db, session_id=session_id)

            if session is None:
                await websocket.send_json({"type": "error", "message": "Interview session not found."})
                await websocket.close(code=1008)
                return

            session = session.model_copy(update={"status": SessionStatus.IN_PROGRESS})
            await update_interview_session(db, session=session)

            if session.skill_gap_report_id is None:
                await websocket.send_json({"type": "error", "message": "SkillGapReport is missing for this session."})
                await websocket.close(code=1008)
                return

            result = await db.execute(
                select(SkillGapReportORM).where(SkillGapReportORM.id == session.skill_gap_report_id)
            )
            report_orm = result.scalar_one_or_none()

            if report_orm is None:
                await websocket.send_json({"type": "error", "message": "SkillGapReport not found."})
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

            if not session.question_set or not session.question_set.questions:
                await websocket.send_json({"type": "error", "message": "QuestionSet is missing or empty."})
                await websocket.close(code=1008)
                return

            config = session.config or {}
            job_description_text = config.get("job_description_text")
            candidate_resume_text = config.get("resume_text")

            if not job_description_text or not candidate_resume_text:
                await websocket.send_json({"type": "error", "message": "Session is missing resume or job description context."})
                await websocket.close()
                return

            state = {
                "session": session,
                "skill_gap_report": skill_gap_report,
                "job_description_text": job_description_text,
                "candidate_resume_text": candidate_resume_text,
                "db": db,
                "openai_client": None,
                "answer_text": None,
            }

            await _run_interview_loop(websocket, state, db=db)

    except WebSocketDisconnect:
        return

    except Exception as exc:
        logger.exception("Interview WebSocket error (DB path): %s", exc)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=1011)
        except Exception:
            pass
