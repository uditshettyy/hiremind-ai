"""
pgvector / embedding helpers (app.utils.vector_store), per ARCHITECTURE.md §3.1.

`embed_texts` is the `embed_fn` that service.py's `_chunk_and_embed` calls.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Sequence

from google import genai
from google.genai import types

from app.config import get_settings


@lru_cache
def _get_gemini_client() -> genai.Client:
    """One Gemini client per process."""
    settings = get_settings()
    return genai.Client(api_key=settings.gemini_api_key)


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Batch-embed strings using Gemini Embedding 001.

    PostgreSQL expects vector(1536), so embeddings are explicitly
    requested at 1536 dimensions.
    """
    if not texts:
        return []

    client = _get_gemini_client()

    def _embed() -> list[list[float]]:
        response = client.models.embed_content(
            model="gemini-embedding-001",
            contents=list(texts),
            config=types.EmbedContentConfig(
                output_dimensionality=1536,
            ),
        )

        return [embedding.values for embedding in response.embeddings]

    return await asyncio.to_thread(_embed)