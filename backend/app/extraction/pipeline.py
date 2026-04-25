"""Orchestrates the extraction loop.

`extract(file_path, db)` is a pure function over inputs + DB reads. The eval
harness imports it directly without starting FastAPI, satisfying the
assignment's "extraction separately testable" requirement.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import CustomField, EntityAlias
from app.extraction.llm_client import LLMMessage, complete_json
from app.extraction.normalize import normalize_extraction
from app.extraction.parse_doc import build_user_parts, build_user_parts_async, guess_mime
from app.extraction.prompts import (
    EXTRACT_PROMPT_VERSION,
    build_extraction_system_prompt,
)

log = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    raw: dict  # what the LLM returned (pre-normalization)
    normalized: dict  # post deterministic alias pass
    prompt_version: str
    model: str
    mime: str
    extra: dict = field(default_factory=dict)


def _load_top_aliases(db: Session, limit: int) -> dict[str, str]:
    rows = (
        db.query(EntityAlias)
        .filter(EntityAlias.kind == "skill")
        .order_by(EntityAlias.frequency.desc())
        .limit(limit)
        .all()
    )
    return {r.alias: r.canonical for r in rows}


def _load_custom_fields(db: Session, jd_id: int | None = None) -> list[dict]:
    """Load the custom fields the model should be told about for this run.

    A field with `job_description_id IS NULL` is global — included on every
    extraction. A field with a specific `job_description_id` is included
    ONLY when the resume is being scored against that JD.
    """
    q = db.query(CustomField)
    if jd_id is None:
        q = q.filter(CustomField.job_description_id.is_(None))
    else:
        q = q.filter(
            (CustomField.job_description_id.is_(None))
            | (CustomField.job_description_id == jd_id)
        )
    rows = q.order_by(CustomField.id.asc()).all()
    return [
        {"name": r.name, "description": r.description, "type": r.type} for r in rows
    ]


async def _emit_progress(
    progress_callback: Callable[[str], object] | None,
    step: str,
) -> None:
    if progress_callback is None:
        return
    maybe = progress_callback(step)
    if inspect.isawaitable(maybe):
        await maybe


def extract(
    file_path: str | Path,
    db: Session,
    *,
    model: str | None = None,
    aliases_override: dict[str, str] | None = None,
    custom_fields_override: list[dict] | None = None,
    jd_id: int | None = None,
) -> ExtractionResult:
    settings = get_settings()
    path = Path(file_path)
    mime = guess_mime(path)

    aliases = aliases_override
    if aliases is None:
        aliases = _load_top_aliases(db, settings.max_alias_injection)
    custom_fields = (
        custom_fields_override
        if custom_fields_override is not None
        else _load_custom_fields(db, jd_id=jd_id)
    )

    system_prompt = build_extraction_system_prompt(
        aliases=aliases, custom_fields=custom_fields)
    user_parts = build_user_parts(path, mime)

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_parts),
    ]
    raw: dict[str, Any] = complete_json(messages, model=model)
    raw = _unwrap_if_nested(raw)
    _apply_extraction_defaults(raw)

    normalized = normalize_extraction(dict(raw), db)
    return ExtractionResult(
        raw=raw,
        normalized=normalized,
        prompt_version=EXTRACT_PROMPT_VERSION,
        model=model or settings.llm_model,
        mime=mime,
    )


_EXPECTED_TOP_LEVEL_KEYS = {
    "contact",
    "education",
    "experience",
    "projects",
    "technical_skills",
}


def _looks_like_extraction(value: Any) -> bool:
    return isinstance(value, dict) and any(
        k in value for k in _EXPECTED_TOP_LEVEL_KEYS
    )


def _unwrap_if_nested(raw: dict[str, Any]) -> dict[str, Any]:
    """Recover the real extraction when the model wraps it in another object.

    Observed failure modes:
      - {"extraction": {...}} or {"resume": {...}} wrapper.
      - The model treats the literal `{}` placeholder in our prompt as a key
        and emits {"{}": {...filled...}, ...empty defaults...}.
      - The model emits {filled extraction} alongside echoed empty defaults
        in the same object — JSON parsers keep the *last* duplicate key, so
        all the filled values get clobbered by the empty echo. We can't
        recover that here (the parser already lost the data) but the changes
        below catch the wrapper-style failures.

    If the top level looks like a real extraction (has any expected key with
    a non-empty value) we keep it as-is. Otherwise we look one level down for
    a wrapper that does.
    """
    if _has_filled_extraction_signal(raw):
        return raw

    for value in raw.values():
        if _has_filled_extraction_signal(value):
            return value  # type: ignore[return-value]

    # Last resort: any nested dict that at least has the right shape.
    for value in raw.values():
        if _looks_like_extraction(value):
            return value  # type: ignore[return-value]
    return raw


def _has_filled_extraction_signal(value: Any) -> bool:
    """True if `value` has any non-empty extraction field at the top level."""
    if not isinstance(value, dict):
        return False
    if isinstance(value.get("contact"), dict) and any(
        value["contact"].get(k) for k in ("name", "email", "phone")
    ):
        return True
    for list_key in ("education", "experience", "projects", "technical_skills"):
        v = value.get(list_key)
        if isinstance(v, list) and len(v) > 0:
            return True
    return False


def _apply_extraction_defaults(raw: dict[str, Any]) -> None:
    """Fill in any keys the model omitted so downstream code is safe."""
    raw.setdefault("is_resume", True)
    raw.setdefault("validity_confidence", 0.5)
    raw.setdefault("validity_reason", "")
    if not isinstance(raw.get("contact"), dict):
        raw["contact"] = {}
    contact = raw["contact"]
    for key in ("name", "email", "phone", "linkedin", "github", "website"):
        contact.setdefault(key, None)
    raw.setdefault("education", [])
    raw.setdefault("experience", [])
    raw.setdefault("projects", [])
    raw.setdefault("technical_skills", [])
    raw.setdefault("awards", [])
    raw.setdefault("certificates", [])
    raw.setdefault("calculated_yoe", None)
    raw.setdefault("concerns", [])
    raw.setdefault("custom", {})


async def extract_async(
    file_path: str | Path,
    db: Session,
    *,
    model: str | None = None,
    aliases_override: dict[str, str] | None = None,
    custom_fields_override: list[dict] | None = None,
    progress_callback: Callable[[str], object] | None = None,
    jd_id: int | None = None,
) -> ExtractionResult:
    """Async variant for API/background processing with progress updates.

    Blocking parsing/model calls are offloaded to worker threads.
    """

    settings = get_settings()
    path = Path(file_path)
    mime = guess_mime(path)

    aliases = aliases_override
    if aliases is None:
        aliases = _load_top_aliases(db, settings.max_alias_injection)
    custom_fields = (
        custom_fields_override
        if custom_fields_override is not None
        else _load_custom_fields(db, jd_id=jd_id)
    )

    system_prompt = build_extraction_system_prompt(
        aliases=aliases, custom_fields=custom_fields)

    await _emit_progress(progress_callback, "Reading document")
    user_parts = await build_user_parts_async(path, mime)

    messages = [
        LLMMessage(role="system", content=system_prompt),
        LLMMessage(role="user", content=user_parts),
    ]

    await _emit_progress(progress_callback, "AI extracting data")
    raw: dict[str, Any] = await asyncio.to_thread(lambda: complete_json(messages, model=model))
    raw = _unwrap_if_nested(raw)
    _apply_extraction_defaults(raw)

    normalized = normalize_extraction(dict(raw), db)
    return ExtractionResult(
        raw=raw,
        normalized=normalized,
        prompt_version=EXTRACT_PROMPT_VERSION,
        model=model or settings.llm_model,
        mime=mime,
    )
