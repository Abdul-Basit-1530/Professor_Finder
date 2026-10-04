"""Pydantic request/response models for the REST API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.url_utils import InvalidURLError, validate_university_url


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ requests
class ResearchStartRequest(BaseModel):
    university_url: str = Field(..., examples=["https://www.example.edu.cn"])
    fields: list[str] = Field(default_factory=list, max_length=40,
                              description="Research fields — used to choose which departments to search")
    custom_fields: list[str] = Field(default_factory=list, max_length=20)
    max_professors: int | None = Field(None, ge=1, le=150)
    force_refresh: bool = False

    @field_validator("university_url")
    @classmethod
    def _valid_url(cls, v: str) -> str:
        try:
            return validate_university_url(v)
        except InvalidURLError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("fields", "custom_fields")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        out = []
        for item in v:
            for part in item.replace("，", ",").split(","):
                part = part.strip()[:80]
                if part and part not in out:
                    out.append(part)
        return out


class EmailRequest(BaseModel):
    student_name: str = Field(..., min_length=1, max_length=120)
    student_background: str = Field(..., min_length=10, max_length=4000,
                                    description="Degree, university, GPA, skills, projects, publications…")
    target_degree: str = Field("Master's", max_length=60)
    research_interest: str = Field(..., min_length=2, max_length=300)
    scholarship: str = Field("Chinese Government Scholarship (CSC)", max_length=120)
    extra_notes: str | None = Field(None, max_length=1000)
    tone: str = Field("formal", pattern="^(formal|warm|concise)$")


# ------------------------------------------------------------------ responses
class ResearchStartResponse(BaseModel):
    job_id: str
    status: str


class StepOut(BaseModel):
    key: str
    label: str
    status: str
    message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class JobOut(ORM):
    id: str
    university_url: str
    university_name: str | None = None
    fields: list[str]
    options: dict
    status: str
    progress: int
    current_step: str | None
    steps: list[StepOut]
    warnings: list[str]
    stats: dict
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class SourceOut(ORM):
    id: int
    entity_type: str
    entity_id: int | None
    supports: str | None
    source_url: str
    source_type: str
    title: str | None
    retrieved_at: datetime


class UniversityOut(BaseModel):
    id: int | None
    name: str | None
    name_chinese: str | None
    official_url: str
    domain: str
    country: str | None
    location: str | None
    verification_status: str
    sources: list[SourceOut]


class DepartmentOut(ORM):
    id: int
    name: str
    name_chinese: str | None
    school: str | None
    url: str | None
    faculty_list_urls: list[str]
    matched_fields: list[str]
    relevance_score: float
    verification_status: str


class ProfessorOut(ORM):
    id: int
    job_id: str
    name: str
    name_chinese: str | None
    name_is_romanized: bool
    position: str | None
    position_original: str | None
    department_id: int | None
    department_name: str | None
    school: str | None
    email: str | None
    email_verified: bool
    email_status: str
    profile_url: str | None
    verification_status: str


class ProfessorDetailOut(ProfessorOut):
    verification_checks: dict
    notes: list[str]
    sources: list[SourceOut]
    university_name: str | None = None


class EmailDraftResponse(ORM):
    id: int
    professor_id: int
    subject: str
    body: str
    generated_by: str
    warnings: list[str]
    created_at: datetime
