"""ORM models.

Design notes
------------
* `universities` is shared across jobs (keyed by registrable domain).
* Everything a research run discovers (departments, professors) is scoped to a
  `research_job`, so every job is a reproducible snapshot tied to the fields the
  user selected. Re-crawls reuse the
  `page_cache` table instead of duplicating entity rows.
* `sources` is polymorphic (entity_type + entity_id) so any entity can cite any
  number of URLs, each with a type, title, retrieval time and the attribute it supports.
* `professors` keep only contact data: name (EN/ZH), position, department,
  publicly listed email and profile URL, plus verification checks.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class University(TimestampMixin, Base):
    __tablename__ = "universities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    official_url: Mapped[str] = mapped_column(String(1024))
    name: Mapped[str | None] = mapped_column(String(512))
    name_chinese: Mapped[str | None] = mapped_column(String(512))
    country: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(512))
    verification_status: Mapped[str] = mapped_column(String(32), default="NOT VERIFIED")


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    university_url: Mapped[str] = mapped_column(String(1024))
    university_id: Mapped[int | None] = mapped_column(
        ForeignKey("universities.id", ondelete="SET NULL"), index=True
    )
    fields: Mapped[list] = mapped_column(JSON, default=list)
    options: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(255))
    steps: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    requester_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    university: Mapped[University | None] = relationship()


class Department(TimestampMixin, Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(512))
    name_chinese: Mapped[str | None] = mapped_column(String(512))
    school: Mapped[str | None] = mapped_column(String(512))
    url: Mapped[str | None] = mapped_column(String(1024))
    faculty_list_urls: Mapped[list] = mapped_column(JSON, default=list)
    matched_fields: Mapped[list] = mapped_column(JSON, default=list)
    relevance_score: Mapped[float] = mapped_column(Float, default=0.0)
    verification_status: Mapped[str] = mapped_column(String(32), default="NOT VERIFIED")


class Professor(TimestampMixin, Base):
    __tablename__ = "professors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    university_id: Mapped[int | None] = mapped_column(ForeignKey("universities.id", ondelete="SET NULL"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(255))
    name_chinese: Mapped[str | None] = mapped_column(String(64))
    name_is_romanized: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[str | None] = mapped_column(String(128))
    position_original: Mapped[str | None] = mapped_column(String(128))
    department_name: Mapped[str | None] = mapped_column(String(512))
    school: Mapped[str | None] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    email_status: Mapped[str] = mapped_column(String(32), default="EMAIL NOT FOUND")
    profile_url: Mapped[str | None] = mapped_column(String(1024))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    verification_status: Mapped[str] = mapped_column(String(32), default="NOT VERIFIED")
    verification_checks: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[list] = mapped_column(JSON, default=list)

    __table_args__ = (Index("ix_professors_job_name", "job_id", "name"),)


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("research_jobs.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(32))  # university|department|professor
    entity_id: Mapped[int | None] = mapped_column(Integer)
    supports: Mapped[str | None] = mapped_column(String(64))  # e.g. "profile", "listed_on_faculty_page"
    source_url: Mapped[str] = mapped_column(String(1024))
    source_type: Mapped[str] = mapped_column(String(32))
    title: Mapped[str | None] = mapped_column(String(512))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_sources_entity", "entity_type", "entity_id"),)


class ResearchResult(Base):
    __tablename__ = "research_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("research_jobs.id", ondelete="CASCADE"), unique=True
    )
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PageCache(Base):
    __tablename__ = "page_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text)
    status_code: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(128))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    html: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str | None] = mapped_column(Text)
    render_mode: Mapped[str] = mapped_column(String(16), default="http")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailDraft(Base):
    __tablename__ = "email_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    professor_id: Mapped[int] = mapped_column(ForeignKey("professors.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    student_profile: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_by: Mapped[str] = mapped_column(String(32))  # "llm" | "template"
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


__all__ = [
    "University",
    "ResearchJob",
    "Department",
    "Professor",
    "Source",
    "ResearchResult",
    "PageCache",
    "EmailDraft",
]
