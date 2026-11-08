"""FastAPI app factory, per ARCHITECTURE.md §4 (app/main.py)."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.evaluation.router import router as evaluation_router
from app.agents.intake.router import router as intake_router
from app.agents.interview.router import router as interview_router
from app.agents.interview.websocket import router as interview_websocket_router
from app.core.database import init_db
from app.orchestration.router import router as orchestration_router

import app.core.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database schema when the application starts."""
    await init_db()
    yield


app = FastAPI(
    title="AI Career Intelligence & Interview Agent",
    lifespan=lifespan,
)

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["health"])
async def health():
    return "ok"


# Module 1 — Intake & Analysis
app.include_router(intake_router)

# Module 2 — Interview Agent
app.include_router(interview_router)
app.include_router(interview_websocket_router)

# Module 3 — Evaluation & Reporting
app.include_router(evaluation_router)

# Phase 6 — End-to-end session orchestration
app.include_router(orchestration_router)
