"""Learn aliases from recruiter corrections.

When the recruiter saves an edited extraction we diff it against the raw
LLM output and turn pair-replacements into `entity_alias` rows.

Example: raw had ["js", "py"], edited became ["JavaScript", "Python"] →
write (js → JavaScript, py → Python) into `entity_alias` with kind="skill".
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import CorrectionLog, EntityAlias


def _upsert_alias(db: Session, alias: str, canonical: str, kind: str) -> None:
    alias_key = alias.strip().lower()
    canonical_v = canonical.strip()
    if not alias_key or not canonical_v or alias_key == canonical_v.lower():
        return
    existing = (
        db.query(EntityAlias)
        .filter(EntityAlias.alias == alias_key, EntityAlias.kind == kind)
        .one_or_none()
    )
    if existing:
        existing.canonical = canonical_v
        existing.frequency += 1
        existing.source = "user_correction"
    else:
        db.add(
            EntityAlias(
                alias=alias_key,
                kind=kind,
                canonical=canonical_v,
                source="user_correction",
                frequency=1,
            )
        )


def learn_from_skill_diff(db: Session, raw_skills: list[str], edited_skills: list[str]) -> int:
    """Positional diff: if raw[i] != edited[i], treat as an alias pair.

    Imperfect (doesn't handle reorderings) but works well for the common case
    where the recruiter corrects values in place. Additions and deletions are
    ignored (not alias signal).
    """
    added = 0
    for raw, edited in zip(raw_skills or [], edited_skills or []):
        if not isinstance(raw, str) or not isinstance(edited, str):
            continue
        if raw.strip().lower() == edited.strip().lower():
            continue
        _upsert_alias(db, raw, edited, kind="skill")
        added += 1
    return added


def learn_from_education_diff(db: Session, raw_edu: list[dict], edited_edu: list[dict]) -> int:
    added = 0
    for raw, edited in zip(raw_edu or [], edited_edu or []):
        if not isinstance(raw, dict) or not isinstance(edited, dict):
            continue
        # Education entries use `institution` in the new schema; older records
        # may still carry `university`, so we accept either as the source field.
        for source_key, kind in (
            ("institution", "university"),
            ("university", "university"),
            ("degree", "degree"),
        ):
            rv, ev = raw.get(source_key), edited.get(source_key)
            if isinstance(rv, str) and isinstance(ev, str):
                if rv.strip().lower() != ev.strip().lower():
                    _upsert_alias(db, rv, ev, kind=kind)
                    added += 1
    return added


def log_correction(
    db: Session, resume_id: int, field_path: str, before: object, after: object
) -> None:
    db.add(
        CorrectionLog(
            resume_id=resume_id,
            field_path=field_path,
            before_value={"v": before} if not isinstance(before, dict) else before,
            after_value={"v": after} if not isinstance(after, dict) else after,
        )
    )
