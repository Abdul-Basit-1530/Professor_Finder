"""Writes agent results to the database incrementally (so partial results survive failures)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m
from app.agents.context import (
    DepartmentInfo,
    ProfessorInfo,
    ResearchContext,
    SourceRef,
    UniversityInfo,
)
from app.agents.verification import email_status


def _add_sources(db: Session, job_id: str, entity_type: str, entity_id: int | None, refs: list[SourceRef]) -> None:
    seen = set()
    for s in refs:
        key = (s.url, s.supports)
        if key in seen:
            continue
        seen.add(key)
        db.add(m.Source(job_id=job_id, entity_type=entity_type, entity_id=entity_id, supports=s.supports,
                        source_url=s.url[:1024], source_type=s.source_type, title=(s.title or None) and s.title[:500],
                        retrieved_at=s.retrieved_at))


def save_university(db: Session, ctx: ResearchContext, info: UniversityInfo) -> None:
    uni = db.scalar(select(m.University).where(m.University.domain == info.domain))
    if uni is None:
        uni = m.University(domain=info.domain, official_url=info.official_url)
        db.add(uni)
    for attr in ("official_url", "name", "name_chinese", "country", "location"):
        val = getattr(info, attr)
        if val:
            setattr(uni, attr, val)
    uni.verification_status = info.verification_status
    db.flush()
    info.db_id = uni.id
    job = db.get(m.ResearchJob, ctx.job_id)
    job.university_id = uni.id
    db.execute(delete(m.Source).where(m.Source.job_id == ctx.job_id, m.Source.entity_type == "university"))
    _add_sources(db, ctx.job_id, "university", uni.id, info.sources)
    db.commit()


def save_departments(db: Session, ctx: ResearchContext, depts: list[DepartmentInfo]) -> None:
    db.execute(delete(m.Department).where(m.Department.job_id == ctx.job_id))
    for d in depts:
        row = m.Department(
            job_id=ctx.job_id, university_id=ctx.university.db_id if ctx.university else None, name=d.name[:512],
            name_chinese=d.name_chinese, school=d.school, url=d.url, faculty_list_urls=d.faculty_list_urls,
            matched_fields=d.matched_fields, relevance_score=d.relevance_score,
            verification_status=d.verification_status)
        db.add(row)
        db.flush()
        d.db_id = row.id
        _add_sources(db, ctx.job_id, "department", row.id, d.sources)
    db.commit()


def save_professors(db: Session, ctx: ResearchContext, profs: list[ProfessorInfo]) -> None:
    """Insert new professors / update existing ones (IDs stay stable during a job)."""
    keep_ids = []
    for rank, p in enumerate(profs):
        row = db.get(m.Professor, p.db_id) if p.db_id else None
        if row is None:
            row = m.Professor(job_id=ctx.job_id)
            db.add(row)
        row.university_id = ctx.university.db_id if ctx.university else None
        row.department_id = p.department.db_id if p.department else None
        row.name = p.name[:255]
        row.name_chinese = p.name_chinese
        row.name_is_romanized = p.name_is_romanized
        row.position = p.position
        row.position_original = p.position_original
        row.department_name = p.department_name
        row.school = p.school
        row.email = p.email
        row.email_verified = p.email_verified
        row.email_status = email_status(p)
        row.profile_url = p.profile_url
        row.sort_order = rank
        row.verification_status = p.verification_status
        row.verification_checks = p.verification_checks
        row.notes = p.notes
        row.updated_at = datetime.now(timezone.utc)
        db.flush()
        p.db_id = row.id
        keep_ids.append(row.id)
        db.execute(delete(m.Source).where(m.Source.entity_type == "professor", m.Source.entity_id == row.id))
        _add_sources(db, ctx.job_id, "professor", row.id, p.sources)
    # Drop rows that were merged away by de-duplication.
    stale = select(m.Professor.id).where(m.Professor.job_id == ctx.job_id, m.Professor.id.not_in(keep_ids or [-1]))
    for pid in db.scalars(stale).all():
        db.delete(db.get(m.Professor, pid))
    db.commit()
