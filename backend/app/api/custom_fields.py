from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import CustomField
from app.db.session import get_db

router = APIRouter(prefix="/api/custom_fields", tags=["custom_fields"])

ALLOWED_TYPES = {"text", "bool", "list", "number"}


class CustomFieldIn(BaseModel):
    name: str
    description: str
    type: str


class CustomFieldOut(BaseModel):
    id: int
    name: str
    description: str
    type: str
    job_description_id: int | None = None


@router.get("", response_model=list[CustomFieldOut])
def list_fields(db: Session = Depends(get_db)):
    return [
        CustomFieldOut(
            id=f.id,
            name=f.name,
            description=f.description,
            type=f.type,
            job_description_id=f.job_description_id,
        )
        for f in db.query(CustomField).order_by(CustomField.id.asc()).all()
    ]


@router.post("", response_model=CustomFieldOut)
def create(body: CustomFieldIn, db: Session = Depends(get_db)):
    """Create a GLOBAL custom field (applies to every extraction).

    To create a JD-scoped custom field, use POST /api/jd/{jd_id}/custom_fields.
    """
    if body.type not in ALLOWED_TYPES:
        raise HTTPException(400, f"type must be one of {sorted(ALLOWED_TYPES)}")
    if not body.name.strip() or not body.description.strip():
        raise HTTPException(400, "name and description required")
    row = CustomField(
        name=body.name.strip(),
        description=body.description.strip(),
        type=body.type,
        job_description_id=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return CustomFieldOut(
        id=row.id,
        name=row.name,
        description=row.description,
        type=row.type,
        job_description_id=row.job_description_id,
    )


@router.delete("/{field_id}")
def delete(field_id: int, db: Session = Depends(get_db)):
    row = db.get(CustomField, field_id)
    if row is None:
        raise HTTPException(404)
    db.delete(row)
    db.commit()
    return {"ok": True}
