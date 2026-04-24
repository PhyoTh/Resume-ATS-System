"""Metric implementations for the eval harness.

- Field-level equality for name/email (case-insensitive exact).
- Normalized equality for university/degree (after lower + punctuation strip).
- Absolute error for years_experience.
- Set F1 for hard_skills (after normalization).
- Spearman rank correlation for JD-pair ranking.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


_PUNCT = re.compile(r"[^\w\s]")


def norm_text(s: str | None) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = _PUNCT.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def email_match(pred: str | None, truth: str | None) -> bool:
    return (pred or "").strip().lower() == (truth or "").strip().lower() and bool(truth)


def name_match(pred: str | None, truth: str | None) -> bool:
    return norm_text(pred) == norm_text(truth) and bool(truth)


def yoe_abs_error(pred: float | None, truth: float | None) -> float | None:
    if pred is None or truth is None:
        return None
    try:
        return abs(float(pred) - float(truth))
    except (TypeError, ValueError):
        return None


@dataclass
class PRF1:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


def skills_f1(pred: list[str], truth: list[str]) -> PRF1:
    p = {norm_text(s) for s in (pred or []) if s}
    t = {norm_text(s) for s in (truth or []) if s}
    tp = len(p & t)
    fp = len(p - t)
    fn = len(t - p)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return PRF1(precision, recall, f1, tp, fp, fn)


def education_match(pred: list[dict], truth: list[dict]) -> float:
    """Fraction of truth entries that have a matching (degree, university) in pred.

    Normalized equality on both fields; at least one must match.
    """
    if not truth:
        return 1.0 if not pred else 0.0
    pred_pairs = {(norm_text(e.get("degree")), norm_text(e.get("institution") or e.get("university"))) for e in (pred or []) if isinstance(e, dict)}
    hits = 0
    for t in truth:
        if not isinstance(t, dict):
            continue
        tp = (norm_text(t.get("degree")), norm_text(t.get("institution") or t.get("university")))
        if tp in pred_pairs:
            hits += 1
        else:
            # Fall back to either match
            for pp in pred_pairs:
                if pp[0] and pp[0] == tp[0]:
                    hits += 1
                    break
                if pp[1] and pp[1] == tp[1]:
                    hits += 1
                    break
    return hits / len(truth)


def spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation. Returns 0.0 if ill-defined."""
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    rx = _ranks(xs)
    ry = _ranks(ys)
    n = len(xs)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    num = sum((rx[i] - mean_x) * (ry[i] - mean_y) for i in range(n))
    den_x = sum((rx[i] - mean_x) ** 2 for i in range(n)) ** 0.5
    den_y = sum((ry[i] - mean_y) ** 2 for i in range(n)) ** 0.5
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


def _ranks(xs: list[float]) -> list[float]:
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    # Handle ties by averaging
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks
