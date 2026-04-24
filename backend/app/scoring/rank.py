"""Score an extracted candidate JSON against a job description via a second LLM call."""
from __future__ import annotations

from dataclasses import dataclass

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


def _to_float_or_none(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
    data = complete_json(messages, model=model)
    return ScoreResult(
        score=_to_float_or_none(data.get("score")),
        subscores=dict(data.get("subscores", {})),
        rationale=str(data.get("rationale", "")),
    )
