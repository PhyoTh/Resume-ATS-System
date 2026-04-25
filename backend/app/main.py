from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import aliases as aliases_router
from app.api import custom_fields as custom_fields_router
from app.api import dashboard as dashboard_router
from app.api import jd as jd_router
from app.api import resumes as resumes_router
from app.config import get_settings
from app.db.models import Base
from app.db.seed import seed_aliases
from app.db.session import SessionLocal, engine

logging.basicConfig(level=logging.INFO)
settings = get_settings()


def _ensure_jd_updated_at_column() -> None:
    """SQLite-only lightweight migration for the new updated_at column.

    `create_all` won't add columns to a pre-existing table. Single-recruiter
    deployment, so we add it inline rather than pulling in Alembic.
    """
    with engine.begin() as conn:
        cols = conn.exec_driver_sql(
            "PRAGMA table_info(job_description)").fetchall()
        names = {row[1] for row in cols}
        if "updated_at" not in names:
            conn.exec_driver_sql(
                "ALTER TABLE job_description ADD COLUMN updated_at DATETIME"
            )
            conn.exec_driver_sql(
                "UPDATE job_description SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP)"
            )


def _ensure_resume_status_column() -> None:
    """Add the recruiter-pipeline `status` column to existing DBs."""
    with engine.begin() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(resume)").fetchall()
        names = {row[1] for row in cols}
        if "status" not in names:
            conn.exec_driver_sql(
                "ALTER TABLE resume ADD COLUMN status VARCHAR(32) DEFAULT 'Ready'"
            )
            conn.exec_driver_sql(
                "UPDATE resume SET status = 'Ready' WHERE status IS NULL"
            )


def _ensure_custom_field_jd_column() -> None:
    """Add the per-JD scope column to existing custom_field tables."""
    with engine.begin() as conn:
        cols = conn.exec_driver_sql(
            "PRAGMA table_info(custom_field)"
        ).fetchall()
        names = {row[1] for row in cols}
        if "job_description_id" not in names:
            conn.exec_driver_sql(
                "ALTER TABLE custom_field ADD COLUMN job_description_id INTEGER REFERENCES job_description(id)"
            )


# Create tables on startup — SQLite, single-recruiter. Alembic hooked in later.
Base.metadata.create_all(engine)
if settings.db_url.startswith("sqlite"):
    _ensure_jd_updated_at_column()
    _ensure_resume_status_column()
    _ensure_custom_field_jd_column()
with SessionLocal() as _db:
    seed_aliases(_db)

app = FastAPI(title="Resume ATS", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "model": settings.llm_model}


app.include_router(jd_router.router)
app.include_router(resumes_router.router)
app.include_router(aliases_router.router)
app.include_router(custom_fields_router.router)
app.include_router(dashboard_router.router)
