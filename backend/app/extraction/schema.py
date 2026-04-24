from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Contact(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None


class EducationEntry(BaseModel):
    institution: str | None = None
    degree: str | None = None
    major: str | None = None
    gpa: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class ExperienceEntry(BaseModel):
    company: str | None = None
    role: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description_bullets: list[str] = Field(default_factory=list)


class ProjectEntry(BaseModel):
    name: str | None = None
    description_bullets: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ExtractedResume(BaseModel):
    is_resume: bool = True
    validity_confidence: float = 1.0
    validity_reason: str = ""

    contact: Contact = Field(default_factory=Contact)
    education: list[EducationEntry] = Field(default_factory=list)
    experience: list[ExperienceEntry] = Field(default_factory=list)
    projects: list[ProjectEntry] = Field(default_factory=list)
    technical_skills: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    calculated_yoe: float | None = None
    concerns: list[str] = Field(default_factory=list)

    custom: dict[str, Any] = Field(default_factory=dict)
