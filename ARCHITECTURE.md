# Architecture

> Paste your actual Phase 0 output into the sections below before either of you
> writes module code. This file is the source of truth both agents build against.

## 1. High-level overview
Modular monolith (single FastAPI app, 3 agent modules) — see README for stack.

## 2. Agents
### Intake & Analysis Agent (Person A)
- Responsibilities:
- Inputs / outputs:

### Interview Agent (Person B)
- Responsibilities:
- Inputs / outputs:

### Evaluation & Reporting Agent (Person A)
- Responsibilities:
- Inputs / outputs:
- **Function signature:**
  ```python
  # paste the agreed function signature here
  ```

## 3. Shared Pydantic models (`/app/models`)
```python
# paste shared schemas here
```

## 4. Database design
- Tables:
- pgvector usage:
- Relationships:

## 5. Folder structure
See README.md — kept in sync with actual repo layout.

## 6. Cross-agent contracts
How Intake & Analysis output feeds Interview Agent input, and how Interview
Agent output feeds Evaluation & Reporting input.
