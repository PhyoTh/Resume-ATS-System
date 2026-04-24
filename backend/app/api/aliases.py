from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import EntityAlias
from app.db.session import get_db

router = APIRouter(prefix="/api/aliases", tags=["aliases"])


class AliasOut(BaseModel):
    alias: str
    kind: str
    canonical: str
    source: str
    frequency: int


class AliasIn(BaseModel):
    alias: str
    canonical: str
    kind: str = "skill"


@router.get("", response_model=list[AliasOut])
def list_aliases(kind: str | None = None, db: Session = Depends(get_db)):
    q = db.query(EntityAlias)
    if kind:
        q = q.filter(EntityAlias.kind == kind)
    rows = q.order_by(EntityAlias.frequency.desc(), EntityAlias.alias.asc()).all()
    return [
        AliasOut(
            alias=r.alias, kind=r.kind, canonical=r.canonical, source=r.source, frequency=r.frequency
        )
        for r in rows
    ]


@router.post("", response_model=AliasOut)
def upsert(body: AliasIn, db: Session = Depends(get_db)):
    key = body.alias.strip().lower()
    if not key or not body.canonical.strip():
        raise HTTPException(400, "alias and canonical must be non-empty")
    existing = (
        db.query(EntityAlias)
        .filter(EntityAlias.alias == key, EntityAlias.kind == body.kind)
        .one_or_none()
    )
    if existing:
        existing.canonical = body.canonical.strip()
        existing.source = "user_correction"
        row = existing
    else:
        row = EntityAlias(
            alias=key,
            kind=body.kind,
            canonical=body.canonical.strip(),
            source="user_correction",
            frequency=1,
        )
        db.add(row)
    db.commit()
    return AliasOut(
        alias=row.alias,
        kind=row.kind,
        canonical=row.canonical,
        source=row.source,
        frequency=row.frequency,
    )


@router.delete("/{kind}/{alias}")
def delete(kind: str, alias: str, db: Session = Depends(get_db)):
    row = (
        db.query(EntityAlias)
        .filter(EntityAlias.alias == alias.lower(), EntityAlias.kind == kind)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404)
    db.delete(row)
    db.commit()
    return {"ok": True}
