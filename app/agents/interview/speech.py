"""Speech-to-text service for the Interview Agent voice layer."""

import asyncio
import io
import logging
from typing import Optional

from app.config import get_settings

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Raised when audio transcription fails, audio is empty/silent, or service is unavailable."""

    pass


def _mime_to_filename(mime_type: str) -> str:
    """Map MIME type to an appropriate filename extension for Whisper transcription."""
    clean = (mime_type or "").lower().strip()
    if "webm" in clean:
        return "audio.webm"
    if "wav" in clean:
        return "audio.wav"
    if "mp3" in clean or "mpeg" in clean:
        return "audio.mp3"
    if "ogg" in clean:
        return "audio.ogg"
    if "m4a" in clean or "mp4" in clean:
        return "audio.m4a"
    if "flac" in clean:
        return "audio.flac"
    return "audio.webm"


def _transcribe_sync(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """Synchronous blocking transcription using Groq Whisper API or faster-whisper.

    Designed to be run off the asyncio event loop via asyncio.to_thread().
    """
    if not audio_bytes or len(audio_bytes) == 0:
        raise TranscriptionError(
            "Audio recording is empty. Please speak clearly and try again."
        )

    # Audio files with header typically need at least 32 bytes to be valid
    if len(audio_bytes) < 32:
        raise TranscriptionError(
            "Audio recording was too short or silent. Please try again."
        )

    settings = get_settings()
    filename = _mime_to_filename(mime_type)

    # 1. Try Groq Whisper API if available and key configured
    groq_api_key = settings.groq_api_key
    if groq_api_key:
        try:
            from groq import Groq

            client = Groq(api_key=groq_api_key)
            transcription = client.audio.transcriptions.create(
                file=(filename, audio_bytes),
                model="whisper-large-v3",
                response_format="json",
            )
            raw_text = getattr(transcription, "text", "") or str(transcription)
            text = raw_text.strip()
            if not text:
                raise TranscriptionError(
                    "No speech detected in audio. Please speak clearly and try again."
                )
            return text
        except TranscriptionError:
            raise
        except Exception as exc:
            logger.error("Groq Whisper transcription failed: %s", exc)
            raise TranscriptionError(
                f"Audio transcription service error: {exc}"
            ) from exc

    # 2. Fallback to faster-whisper if installed locally
    try:
        from faster_whisper import WhisperModel

        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(io.BytesIO(audio_bytes))
        text = " ".join(seg.text for seg in segments).strip()
        if not text:
            raise TranscriptionError(
                "No speech detected in audio. Please speak clearly and try again."
            )
        return text
    except ImportError:
        pass
    except TranscriptionError:
        raise
    except Exception as exc:
        logger.error("faster-whisper transcription failed: %s", exc)
        raise TranscriptionError(
            f"Local transcription error: {exc}"
        ) from exc

    raise TranscriptionError(
        "No transcription provider configured. Please set GROQ_API_KEY in your environment."
    )


async def transcribe_audio(
    audio_bytes: bytes,
    mime_type: str = "audio/webm",
) -> str:
    """Asynchronously transcribes audio bytes off the main event loop."""
    return await asyncio.to_thread(_transcribe_sync, audio_bytes, mime_type)

