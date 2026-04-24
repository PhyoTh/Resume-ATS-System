from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import JobDescription, Resume, ResumeProcessingTask
from app.db.session import get_db

router = APIRouter(prefix="/api/jd", tags=["jd"])


class JDIn(BaseModel):
    title: str
    body_md: str
    required_skills: list[str] = []


class JDOut(BaseModel):
    id: int
    title: str
    body_md: str
    required_skills: list[str]
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_model(cls, j: JobDescription) -> "JDOut":
        return cls(
            id=j.id,
            title=j.title,
            body_md=j.body_md,
            required_skills=list(j.required_skills_json or []),
            created_at=j.created_at,
            updated_at=j.updated_at,
        )


class JDListOut(BaseModel):
    id: int
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_model(cls, j: JobDescription) -> "JDListOut":
        return cls(
            id=j.id,
            title=j.title,
            created_at=j.created_at,
            updated_at=j.updated_at,
        )


@router.get("", response_model=list[JDListOut])
def list_jds(db: Session = Depends(get_db)):
    rows = (
        db.query(JobDescription)
        .order_by(
            JobDescription.updated_at.desc().nullslast(),
            JobDescription.id.desc(),
        )
        .all()
    )
    return [JDListOut.from_model(r) for r in rows]


@router.get("/{jd_id}", response_model=JDOut)
def get_jd(jd_id: int, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")
    return JDOut.from_model(jd)


@router.post("", response_model=JDOut)
def create_jd(body: JDIn, db: Session = Depends(get_db)):
    now = datetime.utcnow()
    jd = JobDescription(
        title=body.title.strip() or "Untitled JD",
        body_md=body.body_md,
        required_skills_json=body.required_skills,
        is_active=False,
        created_at=now,
        updated_at=now,
    )
    db.add(jd)
    db.commit()
    db.refresh(jd)
    return JDOut.from_model(jd)


@router.put("/{jd_id}", response_model=JDOut)
def update_jd(jd_id: int, body: JDIn, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")
    jd.title = body.title.strip() or "Untitled JD"
    jd.body_md = body.body_md
    jd.required_skills_json = body.required_skills
    jd.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(jd)
    return JDOut.from_model(jd)


@router.delete("/{jd_id}")
def delete_jd(jd_id: int, db: Session = Depends(get_db)):
    """Delete a JD AND every resume submitted under it.

    The resume blob on disk is removed too. ResumeProcessingTask rows
    cascade via the relationship's `cascade='all, delete-orphan'`.
    """
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")

    resumes = (
        db.query(Resume).filter(Resume.scored_against_jd_id == jd_id).all()
    )
    for r in resumes:
        # Best-effort: remove the file from disk before the DB row goes.
        if r.storage_path:
            path = Path(r.storage_path)
            if path.exists() and path.is_file():
                try:
                    path.unlink()
                except OSError:
                    pass
        db.delete(r)

    # Tasks may also reference the JD without going through a resume.
    db.query(ResumeProcessingTask).filter(
        ResumeProcessingTask.job_description_id == jd_id,
    ).update({ResumeProcessingTask.job_description_id: None})

    db.delete(jd)
    db.commit()
    return {"ok": True, "deleted_resumes": len(resumes)}
