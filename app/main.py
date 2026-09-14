"""FastAPI app factory, per ARCHITECTURE.md §4 (app/main.py)."""
from fastapi import FastAPI

from app.agents.intake.router import router as intake_router

app = FastAPI(title="AI Career Intelligence & Interview Agent")


@app.get("/health", tags=["health"])
async def health():
    return "ok"


app.include_router(intake_router)

# When Person B's interview router and your evaluation router exist, wire
# them in here the same way:
# from app.agents.interview.router import router as interview_router
# from app.agents.evaluation.router import router as evaluation_router
# app.include_router(interview_router)
# app.include_router(evaluation_router)