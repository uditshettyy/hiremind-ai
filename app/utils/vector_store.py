"""
pgvector / embedding helpers (app.utils.vector_store), per ARCHITECTURE.md §3.1.

`embed_texts` is the `embed_fn` that service.py's `_chunk_and_embed` calls —
wire it in via router.py once ready:

    from app.utils.vector_store import embed_texts

    await analyze_skill_gap(
        ...,
        db_session=db,               # from Depends(get_db)
        embed_fn=embed_texts,
    )
"""
from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from mistralai.client import Mistral  # SDK v2 import path

from app.config import get_settings


@lru_cache
def _get_mistral_client() -> Mistral:
    """One client per process — Mistral() is not free to construct."""
    return Mistral(api_key=get_settings().mistral_api_key)


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Batch-embed strings via Mistral AI embeddings. Isolated for easy mocking in tests."""
    if not texts:
        return []
    client = _get_mistral_client()
    resp = await client.embeddings.create_async(
        model="mistral-embed",
        inputs=list(texts),
    )
    return [d.embedding for d in resp.data]