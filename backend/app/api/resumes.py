from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import (
    CorrectionLog,
    JobDescription,
    Resume,
    ResumeProcessingTask,
)
from app.db.session import SessionLocal, get_db
from app.extraction.parse_doc import guess_mime
from app.extraction.pipeline import extract_async
from app.learning.aliases import (
    learn_from_skill_diff,
    log_correction,
)
from app.scoring.rank import match_tier_for_score, score_candidate

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/resumes", tags=["resumes"])

TASK_QUEUED = "queued"
TASK_PROCESSING = "processing"
TASK_DONE = "done"
TASK_ERROR = "error"

STEP_UPLOADED = "Uploaded"
STEP_READING = "Reading document"
STEP_EXTRACTING = "AI extracting data"
STEP_SCORING = "AI scoring"
STEP_DONE = "Done"
STEP_REJECTED = "Rejected document"
STEP_FAILED = "Failed"

# Recruiter pipeline statuses (for the dashboard dropdown).
# "Ready" is the default state right after extraction completes.
RESUME_STATUSES = (
    "Ready",
    "Recruiter-Call",
    "Round 1",
    "Round 2",
    "Final Round",
    "Rejected",
    "Awaiting Acceptance",
    "Accepted",
)

# Upload safety knobs.
# 10 MB is well above the largest real-world resume (typical PDF resumes
# are 100-300 KB; an image-heavy multi-page CV maxes out around 5 MB).
# Anything bigger is almost certainly a mis-upload or a deliberate DoS.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".png", ".jpg", ".jpeg", ".txt", ".md"}


def _safe_suffix(filename: str | None) -> str:
    """Pull a safe extension from a user-supplied filename.

    `Path(...).suffix` only returns the last dotted segment so path
    traversal characters in the original filename can't leak into the
    storage path, but the suffix itself can still be `.exe`, `.zip`, or
    nonsense — caller decides whether to allow it.
    """
    if not filename:
        return ""
    suffix = Path(filename).suffix.lower()
    # Path separator chars in the suffix would be alarming; strip just in case.
    return re.sub(r"[\\/:]", "", suffix)


def _is_rejected(is_resume: bool, validity_confidence: float) -> bool:
    settings = get_settings()
    return (not is_resume) or (
        validity_confidence < settings.validity_confidence_threshold
    )


def _rejection_reason(is_resume: bool, validity_confidence: float) -> str | None:
    if is_resume and not _is_rejected(is_resume, validity_confidence):
        return None
    if not is_resume:
        return "This document does not appear to be a valid resume."
    return f"Resume confidence is below threshold ({validity_confidence:.2f})."


def _latest_task_for_resume(
    db: Session,
    resume_id: int,
) -> ResumeProcessingTask | None:
    return (
        db.query(ResumeProcessingTask)
        .filter(ResumeProcessingTask.resume_id == resume_id)
        .order_by(
            ResumeProcessingTask.updated_at.desc(),
            ResumeProcessingTask.created_at.desc(),
        )
        .first()
    )


def _latest_task_map(
    db: Session,
    resume_ids: list[int],
) -> dict[int, ResumeProcessingTask]:
    if not resume_ids:
        return {}
    rows = (
        db.query(ResumeProcessingTask)
        .filter(ResumeProcessingTask.resume_id.in_(resume_ids))
        .order_by(
            ResumeProcessingTask.updated_at.desc(),
            ResumeProcessingTask.created_at.desc(),
        )
        .all()
    )
    out: dict[int, ResumeProcessingTask] = {}
    for row in rows:
        if row.resume_id not in out:
            out[row.resume_id] = row
    return out


def _load_selected_jd(db: Session, jd_id: int | None) -> JobDescription | None:
    if jd_id is not None:
        jd = db.get(JobDescription, jd_id)
        if jd is None:
            raise HTTPException(404, "selected JD not found")
        return jd
    return (
        db.query(JobDescription)
        .filter(JobDescription.is_active == True)  # noqa: E712
        .order_by(JobDescription.id.desc())
        .first()
    )


class ResumeOut(BaseModel):
    id: int
    filename: str
    mime_type: str
    is_resume: bool
    validity_confidence: float
    validity_reason: str
    extraction: dict
    extraction_raw: dict
    score: float | None
    match_tier: str | None
    subscores: dict | None
    rationale: str | None
    scored_against_jd_id: int | None
    status: str
    task_id: str | None = None
    processing_status: str | None = None
    processing_step: str | None = None
    processing_error: str | None = None
    is_rejected: bool
    rejection_reason: str | None

    @classmethod
    def from_model(
        cls,
        r: Resume,
        task: ResumeProcessingTask | None = None,
    ) -> "ResumeOut":
        task_is_active = task is not None and task.status in {
            TASK_QUEUED,
            TASK_PROCESSING,
        }
        rejected = False if task_is_active else _is_rejected(
            r.is_resume,
            r.validity_confidence,
        )
        score = None if rejected else r.score
        return cls(
            id=r.id,
            filename=r.filename,
            mime_type=r.mime_type,
            is_resume=r.is_resume,
            validity_confidence=r.validity_confidence,
            validity_reason=r.validity_reason,
            extraction=r.extraction_edited_json or {},
            extraction_raw=r.extraction_raw_json or {},
            score=score,
            match_tier=match_tier_for_score(score),
            subscores=None if rejected else r.subscores_json,
            rationale=None if rejected else r.rank_rationale,
            scored_against_jd_id=r.scored_against_jd_id,
            status=r.status or "Ready",
            task_id=task.id if task else None,
            processing_status=task.status if task else None,
            processing_step=task.step if task else None,
            processing_error=task.error_message if task else None,
            is_rejected=rejected,
            rejection_reason=None
            if task_is_active
            else _rejection_reason(r.is_resume, r.validity_confidence),
        )


class UploadAccepted(BaseModel):
    task_id: str
    resume_id: int
    status: str
    step: str


class TaskOut(BaseModel):
    task_id: str
    resume_id: int
    status: str
    step: str
    error: str | None
    resume: ResumeOut | None


async def _update_task(
    db: Session,
    task: ResumeProcessingTask,
    *,
    status_value: str | None = None,
    step: str | None = None,
    error: str | None = None,
) -> None:
    if status_value is not None:
        task.status = status_value
    if step is not None:
        task.step = step
    task.error_message = error
    task.updated_at = datetime.utcnow()
    db.add(task)
    db.commit()


async def _process_resume_task(task_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(ResumeProcessingTask, task_id)
        if task is None:
            return

        resume = db.get(Resume, task.resume_id)
        if resume is None:
            await _update_task(
                db,
                task,
                status_value=TASK_ERROR,
                step=STEP_FAILED,
                error="resume record not found",
            )
            return

        await _update_task(
            db,
            task,
            status_value=TASK_PROCESSING,
            step=STEP_READING,
            error=None,
        )

        async def _on_progress(step: str) -> None:
            mapped_step = STEP_EXTRACTING if step == STEP_EXTRACTING else step
            await _update_task(
                db,
                task,
                status_value=TASK_PROCESSING,
                step=mapped_step,
                error=None,
            )

        result = await extract_async(
            resume.storage_path,
            db,
            progress_callback=_on_progress,
            jd_id=task.job_description_id,
        )

        resume.mime_type = result.mime
        resume.is_resume = bool(result.raw.get("is_resume", True))
        resume.validity_confidence = float(
            result.raw.get("validity_confidence", 0.0))
        resume.validity_reason = str(result.raw.get("validity_reason", ""))
        resume.extraction_raw_json = result.raw
        resume.extraction_edited_json = result.normalized
        resume.prompt_version = result.prompt_version
        resume.score = None
        resume.subscores_json = None
        resume.rank_rationale = None

        if _is_rejected(resume.is_resume, resume.validity_confidence):
            db.add(resume)
            db.commit()
            await _update_task(
                db,
                task,
                status_value=TASK_DONE,
                step=STEP_REJECTED,
                error=None,
            )
            return

        jd = (
            db.get(JobDescription, task.job_description_id)
            if task.job_description_id
            else None
        )
        if jd is not None:
            await _update_task(
                db,
                task,
                status_value=TASK_PROCESSING,
                step=STEP_SCORING,
                error=None,
            )
            try:
                score_result = await asyncio.to_thread(
                    lambda: score_candidate(
                        jd.body_md,
                        list(jd.required_skills_json or []),
                        result.normalized,
                    )
                )
                resume.score = score_result.score
                resume.subscores_json = score_result.subscores
                resume.rank_rationale = score_result.rationale
                resume.scored_against_jd_id = jd.id
            except Exception as e:
                log.warning(
                    "scoring failed for resume_id=%s: %s", resume.id, e)

        db.add(resume)
        db.commit()
        await _update_task(
            db,
            task,
            status_value=TASK_DONE,
            step=STEP_DONE,
            error=None,
        )
    except Exception as e:
        log.exception("processing task failed: %s", task_id)
        try:
            task = db.get(ResumeProcessingTask, task_id)
            if task is not None:
                task.status = TASK_ERROR
                task.step = STEP_FAILED
                task.error_message = str(e)[:1000]
                task.updated_at = datetime.utcnow()
                db.add(task)
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()


@router.post(
    "/upload",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    jd_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    settings = get_settings()
    suffix = _safe_suffix(file.filename) or ".bin"
    if suffix not in ALLOWED_UPLOAD_SUFFIXES:
        raise HTTPException(
            415,
            f"file type {suffix!r} not allowed; expected one of "
            f"{sorted(ALLOWED_UPLOAD_SUFFIXES)}",
        )

    contents = await file.read()
    if len(contents) == 0:
        raise HTTPException(422, "uploaded file is empty")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"file is too large ({len(contents)} bytes); "
            f"limit is {MAX_UPLOAD_BYTES} bytes",
        )

    storage_path = settings.uploads_dir / f"{uuid.uuid4().hex}{suffix}"
    storage_path.write_bytes(contents)

    selected_jd = _load_selected_jd(db, jd_id)

    resume = Resume(
        filename=file.filename or storage_path.name,
        mime_type=guess_mime(storage_path),
        storage_path=str(storage_path),
        is_resume=True,
        validity_confidence=0.0,
        validity_reason="Processing",
        extraction_raw_json={},
        extraction_edited_json={},
        prompt_version="",
        scored_against_jd_id=selected_jd.id if selected_jd else None,
        status="Ready",
    )
    db.add(resume)
    db.flush()

    task = ResumeProcessingTask(
        id=uuid.uuid4().hex,
        resume_id=resume.id,
        job_description_id=selected_jd.id if selected_jd else None,
        status=TASK_QUEUED,
        step=STEP_UPLOADED,
        error_message=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()

    background_tasks.add_task(_process_resume_task, task.id)
    return UploadAccepted(
        task_id=task.id,
        resume_id=resume.id,
        status=task.status,
        step=task.step,
    )


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: str, db: Session = Depends(get_db)):
    task = db.get(ResumeProcessingTask, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    resume = db.get(Resume, task.resume_id)
    return TaskOut(
        task_id=task.id,
        resume_id=task.resume_id,
        status=task.status,
        step=task.step,
        error=task.error_message,
        resume=ResumeOut.from_model(resume, task) if resume else None,
    )


class ResumeListOut(BaseModel):
    items: list[ResumeOut]
    total: int
    limit: int
    offset: int


@router.get("", response_model=ResumeListOut)
def list_resumes(
    db: Session = Depends(get_db),
    jd_id: int | None = None,
    status_filter: str | None = None,
    tier: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """List resumes with optional JD scope, status, and tier filters.

    Default ordering: highest score first (so Excellent tier comes first),
    then most recently uploaded. The dashboard paginates 50 at a time.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    q = db.query(Resume)
    if jd_id is not None:
        q = q.filter(Resume.scored_against_jd_id == jd_id)
    if status_filter:
        q = q.filter(Resume.status == status_filter)

    # Tier filter is applied in Python because match_tier is derived.
    rows = q.order_by(
        Resume.score.desc().nullslast(),
        Resume.id.desc(),
    ).all()

    if tier:
        rows = [r for r in rows if match_tier_for_score(r.score) == tier]

    total = len(rows)
    page = rows[offset: offset + limit]
    task_map = _latest_task_map(db, [r.id for r in page])
    return ResumeListOut(
        items=[ResumeOut.from_model(r, task_map.get(r.id)) for r in page],
        total=total,
        limit=limit,
        offset=offset,
    )


class StatusUpdate(BaseModel):
    status: str


@router.put("/{resume_id}/status", response_model=ResumeOut)
def update_status(
    resume_id: int,
    body: StatusUpdate,
    db: Session = Depends(get_db),
):
    if body.status not in RESUME_STATUSES:
        raise HTTPException(
            422,
            f"status must be one of {list(RESUME_STATUSES)}",
        )
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404, "resume not found")
    r.status = body.status
    db.commit()
    db.refresh(r)
    task = _latest_task_for_resume(db, resume_id)
    return ResumeOut.from_model(r, task)


@router.get("/_meta/statuses", response_model=list[str])
def list_statuses():
    return list(RESUME_STATUSES)


class ScoreRequest(BaseModel):
    jd_id: int


@router.post("/{resume_id}/score", response_model=ResumeOut)
def score_resume(
    resume_id: int,
    body: ScoreRequest,
    db: Session = Depends(get_db),
):
    """Retroactively score (or re-score) an already-extracted resume.

    Used for parse-only uploads (`scored_against_jd_id` is null) and for
    switching a candidate's scoring to a different JD without re-uploading.
    Synchronous — one LLM call, typically < 15s.
    """
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404, "resume not found")
    if _is_rejected(r.is_resume, r.validity_confidence):
        raise HTTPException(
            422, "rejected documents are not eligible for scoring"
        )
    if not (r.extraction_edited_json or r.extraction_raw_json):
        raise HTTPException(422, "resume has no extraction to score")

    jd = db.get(JobDescription, body.jd_id)
    if jd is None:
        raise HTTPException(404, "JD not found")

    extraction = r.extraction_edited_json or r.extraction_raw_json
    try:
        result = score_candidate(
            jd.body_md,
            list(jd.required_skills_json or []),
            extraction,
        )
    except Exception as e:
        log.warning(
            "retroactive scoring failed for resume_id=%s: %s", resume_id, e)
        raise HTTPException(502, f"scoring failed: {e}")

    r.score = result.score
    r.subscores_json = result.subscores
    r.rank_rationale = result.rationale
    r.scored_against_jd_id = jd.id
    db.commit()
    db.refresh(r)
    task = _latest_task_for_resume(db, resume_id)
    return ResumeOut.from_model(r, task)


@router.post(
    "/{resume_id}/retry",
    response_model=UploadAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_extraction(
    resume_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Re-queue the extraction pipeline for a resume that previously failed.

    Re-uses the already-stored file on disk, so the recruiter does not need
    to find and re-upload the original PDF after a transient LLM error
    (rate limit, 529 Overloaded, timeout).
    """
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404, "resume not found")
    if not r.storage_path or not Path(r.storage_path).exists():
        raise HTTPException(
            410,
            "original file is no longer on disk; please re-upload",
        )

    # Reset the extraction state so the dashboard stops showing stale data
    # while the new task runs. We keep scored_against_jd_id so the re-run
    # scores against the same JD as the original upload.
    r.is_resume = True
    r.validity_confidence = 0.0
    r.validity_reason = "Processing"
    r.extraction_raw_json = {}
    r.extraction_edited_json = {}
    r.score = None
    r.subscores_json = None
    r.rank_rationale = None

    task = ResumeProcessingTask(
        id=uuid.uuid4().hex,
        resume_id=resume_id,
        job_description_id=r.scored_against_jd_id,
        status=TASK_QUEUED,
        step=STEP_UPLOADED,
        error_message=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(task)
    db.commit()

    background_tasks.add_task(_process_resume_task, task.id)
    return UploadAccepted(
        task_id=task.id,
        resume_id=resume_id,
        status=task.status,
        step=task.step,
    )


@router.get("/{resume_id}", response_model=ResumeOut)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404)
    task = _latest_task_for_resume(db, resume_id)
    return ResumeOut.from_model(r, task)


@router.get("/{resume_id}/file")
def get_resume_file(resume_id: int, db: Session = Depends(get_db)):
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404, "resume not found")

    path = Path(r.storage_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "stored file not found")

    return FileResponse(
        path=str(path),
        media_type=r.mime_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{r.filename}"'},
    )


class VerifyBody(BaseModel):
    extraction: dict[str, Any]
    apply_alias_learning: bool = False


@router.put("/{resume_id}/verify", response_model=ResumeOut)
def verify(resume_id: int, body: VerifyBody, db: Session = Depends(get_db)):
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404)

    raw = r.extraction_raw_json or {}
    baseline = r.extraction_edited_json or raw
    edited = body.extraction

    if body.apply_alias_learning:
        learn_from_skill_diff(
            db,
            baseline.get("technical_skills", []),
            edited.get("technical_skills", []),
        )

    diffed_keys = (
        "contact",
        "education",
        "experience",
        "projects",
        "technical_skills",
        "awards",
        "certificates",
        "calculated_yoe",
        "concerns",
    )
    for key in diffed_keys:
        if raw.get(key) != edited.get(key):
            log_correction(db, r.id, key, raw.get(key), edited.get(key))

    r.extraction_edited_json = edited
    if "is_resume" in edited:
        r.is_resume = bool(edited["is_resume"])
    if "validity_confidence" in edited:
        try:
            r.validity_confidence = float(edited["validity_confidence"])
        except (TypeError, ValueError):
            pass
    if "validity_reason" in edited and edited["validity_reason"] is not None:
        r.validity_reason = str(edited["validity_reason"])

    db.commit()
    db.refresh(r)
    task = _latest_task_for_resume(db, resume_id)
    return ResumeOut.from_model(r, task)


@router.delete("")
def delete_rejected_resumes(db: Session = Depends(get_db)):
    """Bulk-delete every resume that the validity gate marked as rejected.

    "Rejected" = `is_resume=false` OR `validity_confidence < threshold`,
    using the same logic the dashboard / Verify page reads from.
    """
    rows = db.query(Resume).all()
    rejected = [r for r in rows if _is_rejected(r.is_resume, r.validity_confidence)]
    if not rejected:
        return {"ok": True, "deleted": 0}

    rejected_ids = [r.id for r in rejected]
    db.query(CorrectionLog).filter(
        CorrectionLog.resume_id.in_(rejected_ids)
    ).delete(synchronize_session=False)

    removed_files = 0
    for r in rejected:
        path = Path(r.storage_path) if r.storage_path else None
        db.delete(r)
        if path and path.exists() and path.is_file():
            try:
                path.unlink()
                removed_files += 1
            except OSError as e:
                log.warning("could not remove file %s: %s", path, e)
    db.commit()
    return {
        "ok": True,
        "deleted": len(rejected),
        "files_removed": removed_files,
    }


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.get(Resume, resume_id)
    if r is None:
        raise HTTPException(404, "resume not found")

    storage = Path(r.storage_path) if r.storage_path else None
    # CorrectionLog has no relationship cascade, and SQLite FK enforcement
    # is on, so we have to clear correction rows explicitly. Otherwise the
    # delete fails with a 500 once the recruiter has saved any edits.
    db.query(CorrectionLog).filter(
        CorrectionLog.resume_id == resume_id
    ).delete(synchronize_session=False)
    db.delete(r)
    db.commit()

    if storage is not None and storage.exists() and storage.is_file():
        try:
            storage.unlink()
        except OSError as e:
            log.warning("could not remove file %s: %s", storage, e)
    return {"ok": True}
