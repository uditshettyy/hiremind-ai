"""Unit tests for speech-to-text service and WebSocket voice boundary."""

import base64
import pytest
from unittest.mock import MagicMock, patch

from app.agents.interview.speech import (
    TranscriptionError,
    _mime_to_filename,
    transcribe_audio,
)
from app.core.schemas import (
    Difficulty,
    InterviewSession,
    InterviewTurn,
    Question,
    QuestionSet,
    QuestionType,
    SessionStatus,
    TurnStatus,
)
from tests.fixtures.sample_session import SKILL_GAP_REPORT


# ============================================================================
# SPEECH SERVICE TESTS
# ============================================================================

def test_mime_to_filename_mappings():
    assert _mime_to_filename("audio/webm") == "audio.webm"
    assert _mime_to_filename("audio/webm;codecs=opus") == "audio.webm"
    assert _mime_to_filename("audio/wav") == "audio.wav"
    assert _mime_to_filename("audio/x-wav") == "audio.wav"
    assert _mime_to_filename("audio/mp3") == "audio.mp3"
    assert _mime_to_filename("audio/mpeg") == "audio.mp3"
    assert _mime_to_filename("audio/ogg") == "audio.ogg"
    assert _mime_to_filename("audio/m4a") == "audio.m4a"
    assert _mime_to_filename("audio/flac") == "audio.flac"
    assert _mime_to_filename("") == "audio.webm"


@pytest.mark.asyncio
async def test_transcribe_audio_empty_bytes_raises():
    with pytest.raises(TranscriptionError, match="empty"):
        await transcribe_audio(b"")


@pytest.mark.asyncio
async def test_transcribe_audio_too_short_raises():
    with pytest.raises(TranscriptionError, match="too short or silent"):
        await transcribe_audio(b"too_short_12345")


@pytest.mark.asyncio
async def test_transcribe_audio_groq_success(monkeypatch):
    dummy_audio = b"0" * 64
    fake_transcript = "This is a verified test transcript of candidate speech."

    # Mock settings with groq api key
    from app.config import Settings
    monkeypatch.setattr(
        "app.agents.interview.speech.get_settings",
        lambda: Settings(groq_api_key="gsk_test_fake_key"),
    )

    # Mock Groq client and its transcription result
    mock_transcription = MagicMock()
    mock_transcription.text = fake_transcript

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_transcription

    with patch("groq.Groq", return_value=mock_client):
        result = await transcribe_audio(dummy_audio, mime_type="audio/webm")
        assert result == fake_transcript
        assert mock_client.audio.transcriptions.create.called


@pytest.mark.asyncio
async def test_transcribe_audio_silent_result_raises(monkeypatch):
    dummy_audio = b"0" * 64

    from app.config import Settings
    monkeypatch.setattr(
        "app.agents.interview.speech.get_settings",
        lambda: Settings(groq_api_key="gsk_test_fake_key"),
    )

    mock_transcription = MagicMock()
    mock_transcription.text = "   "

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_transcription

    with patch("groq.Groq", return_value=mock_client):
        with pytest.raises(TranscriptionError, match="No speech detected"):
            await transcribe_audio(dummy_audio)


@pytest.mark.asyncio
async def test_transcribe_audio_groq_api_failure_raises(monkeypatch):
    dummy_audio = b"0" * 64

    from app.config import Settings
    monkeypatch.setattr(
        "app.agents.interview.speech.get_settings",
        lambda: Settings(groq_api_key="gsk_test_fake_key"),
    )

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.side_effect = RuntimeError("Groq rate limit exceeded")

    with patch("groq.Groq", return_value=mock_client):
        with pytest.raises(TranscriptionError, match="Audio transcription service error"):
            await transcribe_audio(dummy_audio)


@pytest.mark.asyncio
async def test_transcribe_audio_no_provider_configured(monkeypatch):
    dummy_audio = b"0" * 64

    from app.config import Settings
    monkeypatch.setattr(
        "app.agents.interview.speech.get_settings",
        lambda: Settings(groq_api_key=""),
    )

    # Make faster-whisper import fail
    with patch.dict("sys.modules", {"faster_whisper": None}):
        with pytest.raises(TranscriptionError, match="No transcription provider configured"):
            await transcribe_audio(dummy_audio)


# ============================================================================
# WEBSOCKET BOUNDARY INTEGRATION TESTS
# ============================================================================

def make_sample_session():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    q1 = Question(
        question_id="q-001",
        question_text="How do B-tree indexes work in PostgreSQL?",
        question_type=QuestionType.TECHNICAL,
        target_skill="postgres_indexing",
        difficulty=Difficulty.MEDIUM,
        expected_bullet_points=["Ordered nodes", "Range queries"],
    )
    q_set = QuestionSet(
        set_id="qset-001",
        session_id="sess-ws-voice-001",
        questions=[q1],
        created_at=now,
    )
    return InterviewSession(
        session_id="sess-ws-voice-001",
        candidate_id="cand-001",
        job_id="job-001",
        skill_gap_report_id="report-001",
        status=SessionStatus.CREATED,
        question_set=q_set,
        turns=[],
        current_turn_number=0,
        session_started_at=now,
        config={
            "job_description_text": "Backend Engineer role with PostgreSQL.",
            "resume_text": "Experienced Python and PostgreSQL developer.",
        },
    )


@pytest.mark.asyncio
async def test_websocket_accepts_audio_and_sends_transcript(monkeypatch):
    """Verifies that an audio answer is transcribed, transcript message is sent to client,
    and turn is evaluated without modifying graph or schemas."""
    from fastapi.testclient import TestClient
    from app.main import app

    session_obj = make_sample_session()

    # Prevent DB lifespan init
    async def fake_init_db():
        pass
    monkeypatch.setattr("app.core.database.init_db", fake_init_db)
    monkeypatch.setattr("app.main.init_db", fake_init_db)

    # Mock DB functions used in websocket.py
    async def fake_get_session(db, session_id):
        return session_obj

    async def fake_update_session(db, session):
        return session

    async def fake_persist_turn(db, session, turn):
        pass

    monkeypatch.setattr("app.agents.interview.websocket.get_interview_session", fake_get_session)
    monkeypatch.setattr("app.agents.interview.websocket.update_interview_session", fake_update_session)
    monkeypatch.setattr("app.agents.interview.websocket.persist_interview_turn", fake_persist_turn)

    # Mock AsyncSession context manager
    class MockAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def execute(self, query):
            mock_result = MagicMock()
            mock_orm = MagicMock()
            mock_orm.id = "report-001"
            mock_orm.candidate_id = "cand-001"
            mock_orm.job_id = "job-001"
            mock_orm.generated_at = SKILL_GAP_REPORT.generated_at
            mock_orm.overall_match_score = SKILL_GAP_REPORT.overall_match_score
            mock_orm.top_gaps = SKILL_GAP_REPORT.top_gaps
            mock_orm.strengths = SKILL_GAP_REPORT.strengths
            mock_orm.metadata_ = {}
            mock_result.scalar_one_or_none.return_value = mock_orm
            return mock_result

    monkeypatch.setattr("app.agents.interview.websocket.AsyncSessionLocal", lambda: MockAsyncSession())

    from app.core.schemas import AnswerEvaluation, DimensionScore, ScoreDimension
    from datetime import datetime, timezone

    def _make_eval(turn_num: int, score: float, comment: str) -> AnswerEvaluation:
        return AnswerEvaluation(
            evaluation_id=f"eval-{turn_num}",
            session_id="sess-ws-voice-001",
            candidate_id="cand-001",
            turn_number=turn_num,
            overall_score=score,
            weighted_score=score,
            dimension_scores=[
                DimensionScore(dimension=ScoreDimension.ACCURACY, score=score, rationale="Accurate"),
                DimensionScore(dimension=ScoreDimension.DEPTH, score=score, rationale="Good depth"),
                DimensionScore(dimension=ScoreDimension.CLARITY, score=score, rationale="Clear"),
                DimensionScore(dimension=ScoreDimension.RELEVANCE, score=score, rationale="Relevant"),
                DimensionScore(dimension=ScoreDimension.CONFIDENCE, score=score, rationale="Confident"),
            ],
            summary_feedback=comment,
            strengths=["Clear explanation"],
            improvements=[],
            model_answer_snippet="B-trees store sorted keys...",
            routing_hint="next_question",
            evaluated_at=datetime.now(timezone.utc),
            latency_ms=100,
        )

    async def fake_evaluate_turn(state):
        eval_result = _make_eval(1, 8.5, "Great technical explanation.")
        state["session"].turns[-1].evaluation = eval_result
        state["session"].turns[-1].status = TurnStatus.EVALUATED
        return state

    monkeypatch.setattr("app.agents.interview.websocket.evaluate_turn", fake_evaluate_turn)

    # Mock speech transcription
    async def fake_transcribe(audio_bytes, mime_type="audio/webm"):
        return "B-tree indexes maintain sorted key order allowing log N range scans."

    monkeypatch.setattr("app.agents.interview.websocket.transcribe_audio", fake_transcribe)

    # Run WebSocket test via TestClient
    client = TestClient(app)
    with client.websocket_connect("/ws/interview/sess-ws-voice-001") as ws:
        # 1. Server sends connected message
        msg1 = ws.receive_json()
        assert msg1["type"] == "connected"

        # 2. Server sends first question
        msg2 = ws.receive_json()
        assert msg2["type"] == "question"
        assert msg2["turn_number"] == 1

        # 3. Client sends audio message
        dummy_base64 = base64.b64encode(b"RIFF_FAKE_AUDIO_DATA_FOR_SPEECH_TO_TEXT").decode("utf-8")
        ws.send_json({
            "type": "audio_answer",
            "audio_base64": dummy_base64,
            "format": "audio/webm",
        })

        # 4. Server MUST send transcript message back to client
        msg3 = ws.receive_json()
        assert msg3["type"] == "transcript"
        assert msg3["turn_number"] == 1
        assert "B-tree indexes" in msg3["text"]

        # 5. Server sends evaluation
        msg4 = ws.receive_json()
        assert msg4["type"] == "evaluation"
        assert msg4["evaluation"]["overall_score"] == 8.5

        # 6. With only 1 question, route "next_question" completes session
        msg5 = ws.receive_json()
        assert msg5["type"] == "completed"


@pytest.mark.asyncio
async def test_websocket_accepts_standard_text_answer(monkeypatch):
    """Verifies that existing standard text answers continue to work unchanged."""
    from fastapi.testclient import TestClient
    from app.main import app

    session_obj = make_sample_session()

    async def fake_init_db():
        pass
    monkeypatch.setattr("app.core.database.init_db", fake_init_db)
    monkeypatch.setattr("app.main.init_db", fake_init_db)

    async def fake_get_session(db, session_id):
        return session_obj

    async def fake_update_session(db, session):
        return session

    async def fake_persist_turn(db, session, turn):
        pass

    monkeypatch.setattr("app.agents.interview.websocket.get_interview_session", fake_get_session)
    monkeypatch.setattr("app.agents.interview.websocket.update_interview_session", fake_update_session)
    monkeypatch.setattr("app.agents.interview.websocket.persist_interview_turn", fake_persist_turn)

    class MockAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def execute(self, query):
            mock_result = MagicMock()
            mock_orm = MagicMock()
            mock_orm.id = "report-001"
            mock_orm.candidate_id = "cand-001"
            mock_orm.job_id = "job-001"
            mock_orm.generated_at = SKILL_GAP_REPORT.generated_at
            mock_orm.overall_match_score = SKILL_GAP_REPORT.overall_match_score
            mock_orm.top_gaps = SKILL_GAP_REPORT.top_gaps
            mock_orm.strengths = SKILL_GAP_REPORT.strengths
            mock_orm.metadata_ = {}
            mock_result.scalar_one_or_none.return_value = mock_orm
            return mock_result

    monkeypatch.setattr("app.agents.interview.websocket.AsyncSessionLocal", lambda: MockAsyncSession())

    from app.core.schemas import AnswerEvaluation, DimensionScore, ScoreDimension
    from datetime import datetime, timezone

    def _make_eval(turn_num: int, score: float, comment: str) -> AnswerEvaluation:
        return AnswerEvaluation(
            evaluation_id=f"eval-{turn_num}",
            session_id="sess-ws-voice-001",
            candidate_id="cand-001",
            turn_number=turn_num,
            overall_score=score,
            weighted_score=score,
            dimension_scores=[
                DimensionScore(dimension=ScoreDimension.ACCURACY, score=score, rationale="Accurate"),
                DimensionScore(dimension=ScoreDimension.DEPTH, score=score, rationale="Good depth"),
                DimensionScore(dimension=ScoreDimension.CLARITY, score=score, rationale="Clear"),
                DimensionScore(dimension=ScoreDimension.RELEVANCE, score=score, rationale="Relevant"),
                DimensionScore(dimension=ScoreDimension.CONFIDENCE, score=score, rationale="Confident"),
            ],
            summary_feedback=comment,
            strengths=["Clear text explanation"],
            improvements=[],
            model_answer_snippet="B-trees store sorted keys...",
            routing_hint="next_question",
            evaluated_at=datetime.now(timezone.utc),
            latency_ms=100,
        )

    async def fake_evaluate_turn(state):
        eval_result = _make_eval(1, 9.0, "Great text explanation.")
        state["session"].turns[-1].evaluation = eval_result
        state["session"].turns[-1].status = TurnStatus.EVALUATED
        return state

    monkeypatch.setattr("app.agents.interview.websocket.evaluate_turn", fake_evaluate_turn)

    client = TestClient(app)
    with client.websocket_connect("/ws/interview/sess-ws-voice-001") as ws:
        msg1 = ws.receive_json()
        assert msg1["type"] == "connected"

        msg2 = ws.receive_json()
        assert msg2["type"] == "question"

        # Standard text message
        ws.send_json({
            "type": "answer",
            "answer_text": "B-tree indexes maintain balanced tree nodes for range queries.",
        })

        # No transcript message for plain text answers; goes straight to evaluation
        msg3 = ws.receive_json()
        assert msg3["type"] == "evaluation"
        assert msg3["evaluation"]["overall_score"] == 9.0


@pytest.mark.asyncio
async def test_websocket_silent_audio_returns_error_and_allows_retry(monkeypatch):
    """Verifies that empty/silent audio returns an error message and allows the candidate
    to retry sending an answer without breaking the session."""
    from fastapi.testclient import TestClient
    from app.main import app

    session_obj = make_sample_session()

    async def fake_init_db():
        pass
    monkeypatch.setattr("app.core.database.init_db", fake_init_db)
    monkeypatch.setattr("app.main.init_db", fake_init_db)

    async def fake_get_session(db, session_id):
        return session_obj

    async def fake_update_session(db, session):
        return session

    async def fake_persist_turn(db, session, turn):
        pass

    monkeypatch.setattr("app.agents.interview.websocket.get_interview_session", fake_get_session)
    monkeypatch.setattr("app.agents.interview.websocket.update_interview_session", fake_update_session)
    monkeypatch.setattr("app.agents.interview.websocket.persist_interview_turn", fake_persist_turn)

    class MockAsyncSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def execute(self, query):
            mock_result = MagicMock()
            mock_orm = MagicMock()
            mock_orm.id = "report-001"
            mock_orm.candidate_id = "cand-001"
            mock_orm.job_id = "job-001"
            mock_orm.generated_at = SKILL_GAP_REPORT.generated_at
            mock_orm.overall_match_score = SKILL_GAP_REPORT.overall_match_score
            mock_orm.top_gaps = SKILL_GAP_REPORT.top_gaps
            mock_orm.strengths = SKILL_GAP_REPORT.strengths
            mock_orm.metadata_ = {}
            mock_result.scalar_one_or_none.return_value = mock_orm
            return mock_result

    monkeypatch.setattr("app.agents.interview.websocket.AsyncSessionLocal", lambda: MockAsyncSession())

    # Simulated transcribe failure on first attempt, success on second
    call_count = 0
    async def flaky_transcribe(audio_bytes, mime_type="audio/webm"):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise TranscriptionError("No speech detected in audio. Please speak clearly and try again.")
        return "Now I am speaking clearly and answering the question."

    monkeypatch.setattr("app.agents.interview.websocket.transcribe_audio", flaky_transcribe)

    from app.core.schemas import AnswerEvaluation, DimensionScore, ScoreDimension
    from datetime import datetime, timezone

    def _make_eval(turn_num: int, score: float, comment: str) -> AnswerEvaluation:
        return AnswerEvaluation(
            evaluation_id=f"eval-{turn_num}",
            session_id="sess-ws-voice-001",
            candidate_id="cand-001",
            turn_number=turn_num,
            overall_score=score,
            weighted_score=score,
            dimension_scores=[
                DimensionScore(dimension=ScoreDimension.ACCURACY, score=score, rationale="Accurate"),
                DimensionScore(dimension=ScoreDimension.DEPTH, score=score, rationale="Good depth"),
                DimensionScore(dimension=ScoreDimension.CLARITY, score=score, rationale="Clear"),
                DimensionScore(dimension=ScoreDimension.RELEVANCE, score=score, rationale="Relevant"),
                DimensionScore(dimension=ScoreDimension.CONFIDENCE, score=score, rationale="Confident"),
            ],
            summary_feedback=comment,
            strengths=["Clear retry"],
            improvements=[],
            model_answer_snippet="B-trees store sorted keys...",
            routing_hint="next_question",
            evaluated_at=datetime.now(timezone.utc),
            latency_ms=100,
        )

    async def fake_evaluate_turn(state):
        eval_result = _make_eval(1, 8.0, "Good answer after retry.")
        state["session"].turns[-1].evaluation = eval_result
        state["session"].turns[-1].status = TurnStatus.EVALUATED
        return state

    monkeypatch.setattr("app.agents.interview.websocket.evaluate_turn", fake_evaluate_turn)

    client = TestClient(app)
    with client.websocket_connect("/ws/interview/sess-ws-voice-001") as ws:
        ws.receive_json()  # connected
        ws.receive_json()  # question

        # 1. Send silent audio
        ws.send_json({
            "type": "audio_answer",
            "audio_base64": base64.b64encode(b"SILENT_AUDIO_BYTES_00000000000").decode("utf-8"),
        })

        # 2. Server must send error message without closing connection
        err_msg = ws.receive_json()
        assert err_msg["type"] == "error"
        assert "No speech detected" in err_msg["message"]

        # 3. Candidate retries by speaking again
        ws.send_json({
            "type": "audio_answer",
            "audio_base64": base64.b64encode(b"CLEAR_AUDIO_BYTES_11111111111").decode("utf-8"),
        })

        # 4. Server succeeds and sends transcript
        tr_msg = ws.receive_json()
        assert tr_msg["type"] == "transcript"
        assert "Now I am speaking clearly" in tr_msg["text"]

        # 5. Session proceeds to evaluation
        eval_msg = ws.receive_json()
        assert eval_msg["type"] == "evaluation"
        assert eval_msg["evaluation"]["overall_score"] == 8.0
