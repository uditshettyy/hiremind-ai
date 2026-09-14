
"""
Seed the question_bank table from a JSON fixture.
Run: python scripts/seed_question_bank.py
"""
import uuid
import asyncio
import json
import os
from pathlib import Path
from typing import List

import asyncpg
from openai import AsyncOpenAI

# ── Config ──────────────────────────────────────────────────────────
DB_URL = os.getenv("ASYNC_DATABASE_URL", "postgresql://user:pass@localhost:5432/hiremind")
FIXTURE_PATH = Path(__file__).parent.parent / "app" / "fixtures" / "question_bank.json"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BATCH_SIZE = 100  # OpenAI allows up to 2048 per batch, 100 is safe

# ── Helpers ─────────────────────────────────────────────────────────


async def fetch_embedding(client: AsyncOpenAI, texts: List[str]) -> List[List[float]]:
    """Embed a batch of texts using OpenAI."""
    response = await client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


async def seed_questions():
    # 1. Load fixture
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Fixture not found: {FIXTURE_PATH}")

    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    questions = data["questions"]
    print(f"Loaded {len(questions)} questions from fixture.")

    # 2. Init clients
    openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    db = await asyncpg.connect(DB_URL)

    # Ensure pgvector extension exists
    await db.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 3. Embed in batches
    texts = [q["question_text"] for q in questions]
    embeddings: List[List[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        print(f"Embedding batch {i // BATCH_SIZE + 1} ({len(batch)} items)...")
        batch_embeddings = await fetch_embedding(openai_client, batch)
        embeddings.extend(batch_embeddings)

    
    records = []
    for q, emb in zip(questions, embeddings):
        records.append(
            (
                str(uuid.uuid4()),
                q["question_text"],
                q["category"],
                q["question_type"],
                q["difficulty"],
                q.get("target_skills", []),
                json.dumps(q.get("expected_bullet_points", [])),
                q.get("max_duration_seconds", 180),
                "[" + ",".join(map(str, emb)) + "]",
                json.dumps(q.get("metadata", {})),
            )
        )

    await db.executemany(
        """
        INSERT INTO question_bank (

            id,question_text, category, question_type, difficulty,
            target_skills, expected_bullet_points, max_duration_seconds,
            embedding, metadata
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9,$10)
        ON CONFLICT DO NOTHING
        """,
        records,
    )

    count = await db.fetchval("SELECT COUNT(*) FROM question_bank")
    print(f"Done. question_bank now has {count} rows.")

    await db.close()


if __name__ == "__main__":
    asyncio.run(seed_questions())