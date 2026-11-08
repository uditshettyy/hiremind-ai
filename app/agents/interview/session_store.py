"""In-memory session store for no-DB / dev mode.

When the database is unavailable, the WebSocket handler falls back to
sessions created by POST /session/bootstrap and stored here. This avoids
requiring pgvector/Postgres just to run a local dev session.

Sessions are keyed by session_id (str UUID). They expire naturally when
the process restarts (acceptable for dev).
"""
from __future__ import annotations
from typing import Dict, Optional

from app.core.schemas import InterviewSession, SkillGapReport

# {session_id: (InterviewSession, SkillGapReport, resume_text, jd_text)}
_store: Dict[str, tuple[InterviewSession, SkillGapReport, str, str]] = {}


def save(
    session: InterviewSession,
    skill_gap_report: SkillGapReport,
    resume_text: str,
    job_description_text: str,
) -> None:
    _store[str(session.session_id)] = (
        session, skill_gap_report, resume_text, job_description_text
    )


def load(session_id: str) -> Optional[tuple[InterviewSession, SkillGapReport, str, str]]:
    return _store.get(session_id)


def remove(session_id: str) -> None:
    _store.pop(session_id, None)

