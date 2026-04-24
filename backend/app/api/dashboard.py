"""Aggregation endpoints for the dashboard charts + filter metadata."""
from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import Resume
from app.db.session import get_db

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    rows = db.query(Resume).filter(Resume.is_resume == True).all()  # noqa: E712

    skill_counts: Counter[str] = Counter()
    yoe_buckets: Counter[str] = Counter()
    scores: list[float] = []

    for r in rows:
        ex = r.extraction_edited_json or {}
        for s in ex.get("technical_skills", []) or []:
            if isinstance(s, str):
                skill_counts[s] += 1
        yoe = ex.get("calculated_yoe")
        if isinstance(yoe, (int, float)):
            if yoe < 1:
                yoe_buckets["0-1"] += 1
            elif yoe < 3:
                yoe_buckets["1-3"] += 1
            elif yoe < 5:
                yoe_buckets["3-5"] += 1
            elif yoe < 10:
                yoe_buckets["5-10"] += 1
            else:
                yoe_buckets["10+"] += 1
        if r.score is not None:
            scores.append(float(r.score))

    return {
        "total": len(rows),
        "top_skills": [
            {"skill": s, "count": c} for s, c in skill_counts.most_common(20)
        ],
        "yoe_buckets": [
            {"bucket": b, "count": yoe_buckets.get(b, 0)}
            for b in ["0-1", "1-3", "3-5", "5-10", "10+"]
        ],
        "score_histogram": _histogram(scores, bins=10, lo=0, hi=100),
    }


def _histogram(values: list[float], *, bins: int, lo: float, hi: float) -> list[dict]:
    if not values:
        return []
    width = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, max(0, int((v - lo) / width)))
        counts[idx] += 1
    return [
        {"bucket": f"{int(lo + i * width)}-{int(lo + (i + 1) * width)}", "count": counts[i]}
        for i in range(bins)
    ]
