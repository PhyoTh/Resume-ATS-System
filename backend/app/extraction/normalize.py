"""Deterministic post-extraction normalization using the alias table.

Runs after every LLM extraction. Guarantees consistent values for dashboard
filters even if the model ignores the canonical-names prompt block.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import EntityAlias


def load_alias_map(db: Session, kind: str) -> dict[str, str]:
    """Return {lowercased_alias -> canonical} for the given kind."""
    rows = db.query(EntityAlias).filter(EntityAlias.kind == kind).all()
    return {r.alias.lower(): r.canonical for r in rows}


def normalize_skill(skill: str, alias_map: dict[str, str]) -> str:
    key = skill.strip().lower()
    return alias_map.get(key, skill.strip())


def _split_legacy_dates(value: object) -> tuple[str | None, str | None]:
    """Split an old-shape free-text date range into (start, end).

    Best-effort. The new prompt emits start/end directly so this is only
    hit for rows extracted under the previous prompt version.
    """
    if not isinstance(value, str):
        return None, None
    text = value.strip()
    if not text:
        return None, None
    for sep in (" - ", " – ", "—", " to ", "-", "–"):
        if sep in text:
            left, _, right = text.partition(sep)
            return (left.strip() or None, right.strip() or None)
    # Single date → treat as end date (graduation-style).
    return None, text


def _normalize_skill_list(skills: list, skill_map: dict[str, str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for s in skills:
        if not isinstance(s, str) or not s.strip():
            continue
        norm = normalize_skill(s, skill_map)
        key = norm.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(norm)
    return out


def normalize_extraction(extraction: dict, db: Session) -> dict:
    """Mutate + return extraction with skills / institution / degree normalized."""
    skill_map = load_alias_map(db, "skill")
    uni_map = load_alias_map(db, "university")
    degree_map = load_alias_map(db, "degree")

    if isinstance(extraction.get("technical_skills"), list):
        extraction["technical_skills"] = _normalize_skill_list(
            extraction["technical_skills"], skill_map
        )

    if isinstance(extraction.get("education"), list):
        for e in extraction["education"]:
            if not isinstance(e, dict):
                continue
            inst = e.get("institution")
            if isinstance(inst, str):
                e["institution"] = uni_map.get(inst.strip().lower(), inst.strip())
            if isinstance(e.get("degree"), str):
                e["degree"] = degree_map.get(e["degree"].strip().lower(), e["degree"].strip())
            # Legacy shape: graduation_date → end_date.
            if "graduation_date" in e and "end_date" not in e:
                e["end_date"] = e.pop("graduation_date")
            e.setdefault("start_date", None)
            e.setdefault("end_date", None)
            e.setdefault("major", None)
            e.setdefault("gpa", None)

    if isinstance(extraction.get("experience"), list):
        for x in extraction["experience"]:
            if not isinstance(x, dict):
                continue
            # Legacy shape: a single `dates` string → split into start/end.
            if "dates" in x and "start_date" not in x and "end_date" not in x:
                start, end = _split_legacy_dates(x.pop("dates"))
                x["start_date"] = start
                x["end_date"] = end
            x.setdefault("start_date", None)
            x.setdefault("end_date", None)

    if isinstance(extraction.get("projects"), list):
        for p in extraction["projects"]:
            if not isinstance(p, dict):
                continue
            # Migrate older shape: `technologies` → `tags`, `description` (str)
            # → `description_bullets` ([str]).
            if "technologies" in p and "tags" not in p:
                p["tags"] = p.pop("technologies")
            if "description" in p and "description_bullets" not in p:
                desc = p.pop("description")
                p["description_bullets"] = (
                    [desc] if isinstance(desc, str) and desc.strip() else []
                )
            if isinstance(p.get("tags"), list):
                p["tags"] = _normalize_skill_list(p["tags"], skill_map)
            if not isinstance(p.get("description_bullets"), list):
                p["description_bullets"] = []
            if not isinstance(p.get("tags"), list):
                p["tags"] = []

    return extraction
