from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobDescription(Base):
    __tablename__ = "job_description"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(256))
    body_md: Mapped[str] = mapped_column(Text)
    required_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


class Resume(Base):
    __tablename__ = "resume"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(128))
    storage_path: Mapped[str] = mapped_column(String(1024))
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)

    is_resume: Mapped[bool] = mapped_column(Boolean, default=True)
    validity_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    validity_reason: Mapped[str] = mapped_column(Text, default="")

    extraction_raw_json: Mapped[dict] = mapped_column(JSON, default=dict)
    extraction_edited_json: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_version: Mapped[str] = mapped_column(String(32), default="")

    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    subscores_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rank_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)

    scored_against_jd_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_description.id"), nullable=True
    )

    # Pipeline status the recruiter advances manually on the dashboard.
    # See app.api.resumes.RESUME_STATUSES for the allowed values.
    status: Mapped[str] = mapped_column(String(32), default="Ready")

    custom_values: Mapped[list["CustomFieldValue"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )
    processing_tasks: Mapped[list["ResumeProcessingTask"]] = relationship(
        back_populates="resume", cascade="all, delete-orphan"
    )


class ResumeProcessingTask(Base):
    __tablename__ = "resume_processing_task"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"), index=True)
    job_description_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_description.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="queued")  # queued|processing|done|error
    step: Mapped[str] = mapped_column(String(128), default="Uploaded")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)

    resume: Mapped[Resume] = relationship(back_populates="processing_tasks")


class EntityAlias(Base):
    """Unified alias table for skills, universities, degrees.

    `kind` controls scope so the same alias can mean different things per field.
    """

    __tablename__ = "entity_alias"

    alias: Mapped[str] = mapped_column(String(256), primary_key=True)
    kind: Mapped[str] = mapped_column(
        String(32), primary_key=True)  # skill|university|degree
    canonical: Mapped[str] = mapped_column(String(256))
    source: Mapped[str] = mapped_column(
        String(32), default="user_correction")  # seed|user_correction
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


class CustomField(Base):
    __tablename__ = "custom_field"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(16))  # text|bool|list|number
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)


class CustomFieldValue(Base):
    __tablename__ = "custom_field_value"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"))
    custom_field_id: Mapped[int] = mapped_column(ForeignKey("custom_field.id"))
    raw_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    resume: Mapped[Resume] = relationship(back_populates="custom_values")


class CorrectionLog(Base):
    __tablename__ = "correction_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resume.id"))
    field_path: Mapped[str] = mapped_column(String(256))
    before_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_value: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow)
