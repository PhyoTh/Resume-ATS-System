"""Score an extracted candidate JSON against a job description via a second LLM call."""
from __future__ import annotations

from dataclasses import dataclass
import re

from app.extraction.llm_client import LLMMessage, complete_json
from app.extraction.prompts import (
    SCORE_PROMPT_VERSION,
    SCORE_SYSTEM_PROMPT,
    build_score_user_prompt,
)


MATCH_TIERS = ("Excellent", "Good", "Average", "Bad")


def match_tier_for_score(score: float | None) -> str | None:
    """Bucket a 0-100 score into a recruiter-facing tier.

    Cut-offs (decided with the recruiter, see DESIGN.md §match-tiers):
      score >= 90  → Excellent
      score >= 80  → Good
      score >= 40  → Average
      score <  40  → Bad
    Returns None when the score itself is None (e.g. rejected document or
    no JD selected at upload time).
    """
    if score is None:
        return None
    if score >= 90:
        return "Excellent"
    if score >= 80:
        return "Good"
    if score >= 40:
        return "Average"
    return "Bad"


@dataclass
class ScoreResult:
    score: float | None
    subscores: dict
    rationale: str
    prompt_version: str = SCORE_PROMPT_VERSION


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _clamp_score(value: float) -> float:
    return max(0.0, min(100.0, value))


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        m = _NUM_RE.search(value)
        if not m:
            return None
        try:
            return float(m.group(0))
        except (TypeError, ValueError):
            return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.strip().lower()).strip()


def _extract_candidate_skills(extraction: dict) -> set[str]:
    out: set[str] = set()
    for raw in extraction.get("technical_skills", []) or []:
        if isinstance(raw, str):
            token = _normalize_token(raw)
            if token:
                out.add(token)
    for proj in extraction.get("projects", []) or []:
        if not isinstance(proj, dict):
            continue
        for raw in proj.get("tags", []) or []:
            if isinstance(raw, str):
                token = _normalize_token(raw)
                if token:
                    out.add(token)
    return out


_YEAR_RANGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)",
    re.IGNORECASE,
)
_YEAR_SINGLE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)",
    re.IGNORECASE,
)


def _infer_required_years(jd_body: str) -> float | None:
    ranges = [
        (float(a), float(b))
        for a, b in _YEAR_RANGE_RE.findall(jd_body or "")
    ]
    if ranges:
        highs = [max(a, b) for a, b in ranges]
        return max(highs)
    singles = [float(x) for x in _YEAR_SINGLE_RE.findall(jd_body or "")]
    if singles:
        return max(singles)
    return None


def _deterministic_score(
    jd_body: str,
    required_skills: list[str],
    extraction: dict,
) -> ScoreResult:
    req = {
        _normalize_token(s)
        for s in required_skills or []
        if isinstance(s, str) and _normalize_token(s)
    }
    cand = _extract_candidate_skills(extraction)
    if req:
        overlap = len(req & cand) / len(req)
        skills = _clamp_score(round(overlap * 100.0, 1))
    else:
        skills = 70.0 if cand else 40.0

    yoe = _to_float_or_none(extraction.get("calculated_yoe"))
    target_years = _infer_required_years(jd_body)
    if yoe is None:
        experience = 55.0
    elif target_years is None:
        experience = _clamp_score(50.0 + (yoe * 8.0))
    else:
        ratio = yoe / max(target_years, 0.5)
        if ratio >= 1.0:
            experience = _clamp_score(85.0 + min((ratio - 1.0) * 20.0, 15.0))
        else:
            experience = _clamp_score(85.0 * ratio)

    edu_entries = [e for e in extraction.get(
        "education", []) or [] if isinstance(e, dict)]
    has_edu = len(edu_entries) > 0
    degrees_text = " ".join(
        str(e.get("degree") or "") for e in edu_entries
    ).lower()
    jd_l = (jd_body or "").lower()
    if not has_edu:
        education = 35.0
    elif "phd" in jd_l or "doctor" in jd_l:
        education = 95.0 if (
            "phd" in degrees_text or "doctor" in degrees_text) else 60.0
    elif "master" in jd_l or "m.s" in jd_l or "ms" in jd_l:
        education = 90.0 if (
            "master" in degrees_text or "phd" in degrees_text) else 65.0
    elif "bachelor" in jd_l or "b.s" in jd_l or "bs" in jd_l or "ba" in jd_l:
        education = 85.0 if (
            "bachelor" in degrees_text
            or "master" in degrees_text
            or "phd" in degrees_text
            or "doctor" in degrees_text
        ) else 60.0
    else:
        education = 75.0

    overall = _clamp_score(
        round((0.60 * skills) + (0.25 * experience) + (0.15 * education), 1))
    matched = len(req & cand)
    total_req = len(req)
    rationale = (
        "Deterministic fallback scoring used. "
        f"Matched {matched}/{total_req} required skills; "
        f"estimated experience score {experience:.1f}; "
        f"education score {education:.1f}."
    )
    return ScoreResult(
        score=overall,
        subscores={
            "skills": skills,
            "experience": experience,
            "education": education,
        },
        rationale=rationale,
    )


def score_candidate(
    jd_body: str,
    required_skills: list[str],
    extraction: dict,
    *,
    model: str | None = None,
) -> ScoreResult:
    user_prompt = build_score_user_prompt(jd_body, required_skills, extraction)
    messages = [
        LLMMessage(role="system", content=SCORE_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_prompt),
    ]
    try:
        data = complete_json(messages, model=model)
    except Exception:
        return _deterministic_score(jd_body, required_skills, extraction)

    parsed_score = _to_float_or_none(data.get("score"))
    if parsed_score is None:
        return _deterministic_score(jd_body, required_skills, extraction)

    parsed_subscores = dict(data.get("subscores", {}))
    parsed_rationale = str(data.get("rationale", "")).strip()
    return ScoreResult(
        score=_clamp_score(parsed_score),
        subscores=parsed_subscores,
        rationale=parsed_rationale or "LLM score generated.",
    )
