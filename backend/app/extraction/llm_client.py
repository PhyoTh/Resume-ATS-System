"""TritonAI client adapter (OpenAI-compatible).

CSE 190 provides an OpenAI-compatible gateway at TRITON_BASE_URL. We use the
`openai` Python SDK pointed at it. Keeping this thin so swapping providers later
is a single file change.
"""
from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI

from app.config import get_settings

log = logging.getLogger(__name__)

_PREFERRED_FALLBACK_MODELS = (
    "claude-sonnet-4-6",
    "claude-sonnet-4-6-aws",
    "claude-opus-4-6-v1",
)


@dataclass
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: Any  # str or list[dict] for multi-modal parts


def _build_client(api_key: str | None = None, base_url: str | None = None) -> OpenAI:
    settings = get_settings()
    return OpenAI(
        api_key=api_key or settings.triton_api_key or "missing",
        base_url=base_url or settings.triton_base_url,
        timeout=settings.llm_timeout_seconds,
    )


def image_part_from_path(path: Path) -> dict:
    """Build an OpenAI-compatible image_url part from a local image file."""
    ext = path.suffix.lower().lstrip(".") or "png"
    mime = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def _is_model_access_error(err: Exception) -> bool:
    msg = str(err).lower()
    return (
        "team not allowed to access model" in msg
        or "team_model_access_denied" in msg
        or "model not found" in msg
    )


def _select_accessible_fallback_model(client: OpenAI, blocked_model: str) -> str | None:
    try:
        resp = client.models.list()
    except Exception as e:
        log.warning("Could not list models for fallback selection: %s", e)
        return None

    available = [m.id for m in resp.data if getattr(m, "id", None)]
    if not available:
        return None

    # Try known Claude ids first so output quality remains close to default behavior.
    for candidate in _PREFERRED_FALLBACK_MODELS:
        if candidate != blocked_model and candidate in available:
            return candidate

    # Otherwise pick any available Claude model.
    for candidate in available:
        if candidate != blocked_model and "claude" in candidate.lower():
            return candidate

    # Last resort: first available model different from the blocked one.
    for candidate in available:
        if candidate != blocked_model:
            return candidate
    return None


def _create_completion(
    *,
    client: OpenAI,
    model: str,
    payload: list[dict[str, Any]],
    temperature: float,
):
    try:
        return client.chat.completions.create(
            model=model,
            messages=payload,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        if _is_model_access_error(e):
            raise
        log.warning(
            "response_format=json_object rejected (%s); retrying without", e)
        return client.chat.completions.create(
            model=model,
            messages=payload,
            temperature=temperature,
        )


def complete_json(
    messages: list[LLMMessage],
    *,
    model: str | None = None,
    temperature: float | None = None,
) -> dict:
    """Run a chat completion and parse JSON out of the response.

    We request `response_format=json_object` but fall back to best-effort parse
    if the gateway doesn't support it.
    """
    settings = get_settings()
    client = _build_client()
    model = model or settings.llm_model
    temperature = settings.llm_temperature if temperature is None else temperature

    payload = [{"role": m.role, "content": m.content} for m in messages]
    try:
        resp = _create_completion(
            client=client,
            model=model,
            payload=payload,
            temperature=temperature,
        )
    except Exception as e:
        if not _is_model_access_error(e):
            raise
        fallback_model = _select_accessible_fallback_model(
            client, blocked_model=model)
        if not fallback_model:
            raise
        log.warning("Model %s unavailable; retrying with %s",
                    model, fallback_model)
        resp = _create_completion(
            client=client,
            model=fallback_model,
            payload=payload,
            temperature=temperature,
        )

    content = resp.choices[0].message.content or "{}"
    return _parse_json_loose(content)


def _parse_json_loose(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Strip code-fences
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # Best-effort: find first { ... last }
    first, last = text.find("{"), text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return json.loads(text[first: last + 1])
    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]!r}")
