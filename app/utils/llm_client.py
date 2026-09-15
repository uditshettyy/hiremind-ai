"""
Unified LLM client (app.utils.llm_client), per ARCHITECTURE.md §7.

Default provider: Groq, model "llama-3.3-70b-versatile" — good free-tier
rate limits for dev/testing, fast inference. Check https://console.groq.com
for current available models if this one gets deprecated/renamed later.

Implements `generate_structured`, the exact callable signature the intake
module expects (system_prompt, user_prompt, response_model) -> validated
Pydantic instance.
"""
from __future__ import annotations

import asyncio
import json
from typing import Type, TypeVar

from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 3


class LLMError(Exception):
    """Raised when the LLM call fails or returns output that won't validate."""


class LLMRateLimitError(LLMError):
    """Raised when retries on a 429 are exhausted."""


def _is_rate_limit_error(exc: Exception) -> bool:
    """Providers throw different exception types for 429s — check by message
    rather than importing every SDK's specific error class."""
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "rate_limited" in text


async def _call_with_retry(fn, *, timeout_seconds: int):
    """Retries a provider call on rate limits with exponential backoff
    (1s, 2s, 4s). Re-raises immediately on any other error."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout_seconds)
        except Exception as exc:  # noqa: BLE001 — deliberately broad, see re-raise below
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    raise LLMRateLimitError(f"Rate limit retries exhausted: {last_exc}") from last_exc


async def _raw_completion(
    *, system_prompt: str, user_prompt: str, model: str, temperature: float, timeout_seconds: int, response_model: Type[BaseModel],
) -> str:
    """Provider call, isolated so tests can monkeypatch just this function."""
    settings = get_settings()
    provider = settings.llm_provider

    if provider == "groq":
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.groq_api_key)

        async def _call():
            kwargs = {
                "model": model,
                "temperature": temperature,
                "max_completion_tokens": 8192,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                    },
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if "o1" in model.lower() or "o3" in model.lower() or "r1" in model.lower():
                kwargs["reasoning_effort"] = "low"
            return await client.chat.completions.create(**kwargs)

        resp = await _call_with_retry(_call, timeout_seconds=timeout_seconds)
        return resp.choices[0].message.content

    elif provider == "mistralai":
        from mistralai.client import Mistral

        client = Mistral(api_key=settings.mistral_api_key)

        async def _call():
            return await client.chat.complete_async(
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt + "\n\nRespond with ONLY a JSON object, no markdown fences."},
                    {"role": "user", "content": user_prompt},
                ],
            )

        resp = await _call_with_retry(_call, timeout_seconds=timeout_seconds)
        return resp.choices[0].message.content

    elif provider == "anthropic":
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        async def _call():
            return await client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=temperature,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

        resp = await _call_with_retry(_call, timeout_seconds=timeout_seconds)
        return resp.content[0].text

    else:
        raise LLMError(f"Unknown llm_provider: {provider!r}")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


async def generate_structured(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    model: str | None = None,
    temperature: float = 0.1,
    timeout_seconds: int = 30,
) -> T:
    """Call the LLM and validate its JSON response against `response_model`."""
    settings = get_settings()
    resolved_model = model or settings.default_llm_model

    raw = await _raw_completion(
        system_prompt=system_prompt, user_prompt=user_prompt,
        model=resolved_model, temperature=temperature, timeout_seconds=timeout_seconds,
        response_model=response_model,
    )

    for attempt_prompt, attempt_temp in ((user_prompt, temperature), (None, 0.0)):
        try:
            data = json.loads(_strip_fences(raw))
            return response_model.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt_prompt is None:
                raise LLMError(
                    f"LLM response did not validate against {response_model.__name__} "
                    f"after retry: {e}"
                ) from e
            retry_user = (
                f"{user_prompt}\n\nYour previous response was invalid ({e}):\n{raw}\n"
                "Respond again with ONLY valid JSON matching the required shape."
            )
            raw = await _raw_completion(
                system_prompt=system_prompt, user_prompt=retry_user,
                model=resolved_model, temperature=0.0, timeout_seconds=timeout_seconds,
                response_model=response_model,
            )