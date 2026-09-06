# HIREMIND-AI

Multi-agent system for resume/JD analysis, skill-gap detection, and RAG-grounded
agentic interview practice.

## Status
🚧 Early scaffolding — architecture and module skeleton only. No functional code yet.

## Architecture
See [ARCHITECTURE.md](./ARCHITECTURE.md) for schemas, DB design, and agent
function signatures.

## Structure
```
/app
  /agents
    /intake_analysis/      <- Resume + JD parsing, skill-gap detection (Person A)
    /interview/             <- RAG question generation + conversational loop (Person B)
    /evaluation_reporting/  <- Scoring + final report (Person A)
  /core          shared config, DB connection, settings
  /models        shared Pydantic models
  /api           route registration
  main.py
/fixtures        sample resumes, JDs, skill-gap JSON, etc.
/tests
```

## Stack
- FastAPI (modular monolith)
- PostgreSQL + pgvector
- React (frontend, separate concern)

## Getting started
```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in real values
docker-compose up -d            # starts Postgres+pgvector
uvicorn app.main:app --reload
```

## Team
- **Person A** — Intake & Analysis Agent, Evaluation & Reporting Agent
- **Person B** — Interview Agent
