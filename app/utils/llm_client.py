"""
Unified LLM client (app.utils.llm_client), per ARCHITECTURE.md §7.

Default provider: Groq, model "llama-3.3-70b-versatile" — good free-tier
rate limits for dev/testing, fast inference. Check https://console.groq.com
for current available models if this one gets deprecated/renamed later.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel

from app.config import get_settings

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 3


class LLMError(Exception):
    """Raised when the LLM call fails or returns output that won't validate."""


class LLMRateLimitError(LLMError):
    """Raised when retries on a 429 are exhausted."""


class StructuredLLMError(LLMError):
    """Raised when the LLM response can't be parsed as the requested JSON shape."""


class GenerateStructured(Protocol):
    async def __call__(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str = "gpt-4o",
        temperature: float = 0.2,
    ) -> dict[str, Any]: ...


def _is_rate_limit_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "rate_limited" in text


async def _call_with_retry(fn, *, timeout_seconds: int):
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await asyncio.wait_for(fn(), timeout=timeout_seconds)
        except Exception as exc:
            last_exc = exc
            if _is_rate_limit_error(exc) and attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            raise
    raise LLMRateLimitError(f"Rate limit retries exhausted: {last_exc}") from last_exc


async def _raw_completion(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    timeout_seconds: int,
    response_model: Optional[Type[BaseModel]] = None,
) -> str:
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
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
            if response_model is not None:
                kwargs["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": response_model.__name__,
                        "schema": response_model.model_json_schema(),
                    },
                }
            else:
                kwargs["response_format"] = {"type": "json_object"}

            if any(x in model.lower() for x in ("o1", "o3", "r1")):
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


def parse_json_response(raw_text: str) -> dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        stripped = raw_text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:]
            try:
                return json.loads(stripped.strip())
            except json.JSONDecodeError:
                pass
        raise StructuredLLMError(f"Could not parse LLM output as JSON: {exc}") from exc


async def generate_structured(
    *,
    system_prompt: str,
    user_prompt: str,
    response_model: Optional[Type[T]] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    timeout_seconds: int = 30,
) -> Any:
    """Call the LLM and return validated Pydantic model (if response_model passed) or parsed dict."""
    settings = get_settings()
    resolved_model = model or settings.default_llm_model

    if settings.llm_provider == "groq" and ("gpt" in resolved_model.lower() or resolved_model == "gpt-4o"):
        resolved_model = settings.default_llm_model or "llama-3.3-70b-versatile"

    raw = await _raw_completion(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=resolved_model,
        temperature=temperature,
        timeout_seconds=timeout_seconds,
        response_model=response_model,
    )

    data = parse_json_response(_strip_fences(raw))
    if response_model is not None:
        try:
            return response_model.model_validate(data)
        except Exception as e:
            raise StructuredLLMError(f"LLM response did not validate against {response_model.__name__}: {e}") from e

    return data
