import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import (
    CorrectionLog,
    CustomField,
    CustomFieldValue,
    JobDescription,
    Resume,
    ResumeProcessingTask,
)
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
    resume_ids = [r.id for r in resumes]

    custom_fields = (
        db.query(CustomField).filter(
            CustomField.job_description_id == jd_id).all()
    )
    custom_field_ids = [f.id for f in custom_fields]

    if resume_ids:
        db.query(CustomFieldValue).filter(
            CustomFieldValue.resume_id.in_(resume_ids)
        ).delete(synchronize_session=False)
    if resume_ids:
        # CorrectionLog has no relationship cascade; clear it explicitly so
        # the FK-on SQLite enforcement doesn't reject the resume deletes.
        db.query(CorrectionLog).filter(
            CorrectionLog.resume_id.in_(resume_ids)
        ).delete(synchronize_session=False)

    if custom_field_ids:
        db.query(CustomFieldValue).filter(
            CustomFieldValue.custom_field_id.in_(custom_field_ids)
        ).delete(synchronize_session=False)
        db.query(CustomField).filter(
            CustomField.id.in_(custom_field_ids)
        ).delete(synchronize_session=False)

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


# ---------------------------------------------------------------------------
# Per-JD custom fields
# ---------------------------------------------------------------------------

ALLOWED_CUSTOM_FIELD_TYPES = {"text", "bool", "list", "number"}


class CustomFieldIn(BaseModel):
    name: str
    description: str
    type: str


class CustomFieldOut(BaseModel):
    id: int
    name: str
    description: str
    type: str
    job_description_id: int | None


def _custom_field_out(f: CustomField) -> CustomFieldOut:
    return CustomFieldOut(
        id=f.id,
        name=f.name,
        description=f.description,
        type=f.type,
        job_description_id=f.job_description_id,
    )


@router.get("/{jd_id}/custom_fields", response_model=list[CustomFieldOut])
def list_jd_custom_fields(jd_id: int, db: Session = Depends(get_db)):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")
    rows = (
        db.query(CustomField)
        .filter(CustomField.job_description_id == jd_id)
        .order_by(CustomField.id.asc())
        .all()
    )
    return [_custom_field_out(f) for f in rows]


@router.post("/{jd_id}/custom_fields", response_model=CustomFieldOut)
def create_jd_custom_field(
    jd_id: int,
    body: CustomFieldIn,
    db: Session = Depends(get_db),
):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")
    if body.type not in ALLOWED_CUSTOM_FIELD_TYPES:
        raise HTTPException(
            422,
            f"type must be one of {sorted(ALLOWED_CUSTOM_FIELD_TYPES)}",
        )
    name = body.name.strip()
    description = body.description.strip()
    if not name or not description:
        raise HTTPException(422, "name and description are required")
    # Names should be unique within a JD; collisions confuse the prompt.
    clash = (
        db.query(CustomField)
        .filter(
            CustomField.job_description_id == jd_id,
            CustomField.name == name,
        )
        .first()
    )
    if clash:
        raise HTTPException(
            409, f"a custom field named {name!r} already exists for this JD")

    row = CustomField(
        name=name,
        description=description,
        type=body.type,
        job_description_id=jd_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    jd.updated_at = datetime.utcnow()
    db.commit()
    return _custom_field_out(row)


@router.put(
    "/{jd_id}/custom_fields/{field_id}",
    response_model=CustomFieldOut,
)
def update_jd_custom_field(
    jd_id: int,
    field_id: int,
    body: CustomFieldIn,
    db: Session = Depends(get_db),
):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")
    row = db.get(CustomField, field_id)
    if row is None or row.job_description_id != jd_id:
        raise HTTPException(404, "custom field not found for this JD")
    if body.type not in ALLOWED_CUSTOM_FIELD_TYPES:
        raise HTTPException(
            422,
            f"type must be one of {sorted(ALLOWED_CUSTOM_FIELD_TYPES)}",
        )
    name = body.name.strip()
    description = body.description.strip()
    if not name or not description:
        raise HTTPException(422, "name and description are required")
    if name != row.name:
        clash = (
            db.query(CustomField)
            .filter(
                CustomField.job_description_id == jd_id,
                CustomField.name == name,
                CustomField.id != field_id,
            )
            .first()
        )
        if clash:
            raise HTTPException(
                409,
                f"a custom field named {name!r} already exists for this JD",
            )
    row.name = name
    row.description = description
    row.type = body.type
    db.commit()
    db.refresh(row)
    jd.updated_at = datetime.utcnow()
    db.commit()
    return _custom_field_out(row)


@router.delete("/{jd_id}/custom_fields/{field_id}")
def delete_jd_custom_field(
    jd_id: int,
    field_id: int,
    db: Session = Depends(get_db),
):
    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")
    row = db.get(CustomField, field_id)
    if row is None or row.job_description_id != jd_id:
        raise HTTPException(404, "custom field not found for this JD")
    db.delete(row)
    jd.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Re-extract every resume scoped to this JD
# (e.g. after the recruiter added or modified custom fields)
# ---------------------------------------------------------------------------


class ReextractAccepted(BaseModel):
    queued: int
    task_ids: list[str]


@router.post(
    "/{jd_id}/reextract",
    response_model=ReextractAccepted,
    status_code=202,
)
def reextract_jd(
    jd_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Re-queue extraction for every resume scored against this JD.

    Used when the recruiter adds / modifies custom fields and wants the
    historical resumes to be re-parsed under the new prompt.
    """
    # Imported lazily to avoid a circular import (resumes.py imports jd-related
    # models, and this module already pulls JobDescription from models.py).
    from app.api.resumes import (
        STEP_UPLOADED,
        TASK_QUEUED,
        _process_resume_task,
    )

    jd = db.get(JobDescription, jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")

    resumes = (
        db.query(Resume).filter(Resume.scored_against_jd_id == jd_id).all()
    )
    queued: list[str] = []
    now = datetime.utcnow()
    for r in resumes:
        if not r.storage_path or not Path(r.storage_path).exists():
            continue  # original file is gone; skip rather than fail.
        # Reset the extraction state so the dashboard doesn't render stale
        # data while the new task runs.
        r.extraction_raw_json = {}
        r.extraction_edited_json = {}
        r.score = None
        r.subscores_json = None
        r.rank_rationale = None
        r.validity_reason = "Re-processing"

        task = ResumeProcessingTask(
            id=uuid.uuid4().hex,
            resume_id=r.id,
            job_description_id=jd_id,
            status=TASK_QUEUED,
            step=STEP_UPLOADED,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        db.add(task)
        queued.append(task.id)
    db.commit()

    for task_id in queued:
        background_tasks.add_task(_process_resume_task, task_id)
    return ReextractAccepted(queued=len(queued), task_ids=queued)
