"""Assembles the structured research output (used by the API, exports and research_results)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import schemas as s


def sources_for(db: Session, job_id: str, entity_type: str, entity_id: int | None = None) -> list[m.Source]:
    q = select(m.Source).where(m.Source.job_id == job_id, m.Source.entity_type == entity_type)
    if entity_id is not None:
        q = q.where(m.Source.entity_id == entity_id)
    return list(db.scalars(q.order_by(m.Source.id)).all())


def university_payload(db: Session, job: m.ResearchJob) -> s.UniversityOut | None:
    uni = db.get(m.University, job.university_id) if job.university_id else None
    if uni is None:
        return None
    return s.UniversityOut(
        id=uni.id, name=uni.name, name_chinese=uni.name_chinese, official_url=uni.official_url, domain=uni.domain,
        country=uni.country, location=uni.location, verification_status=uni.verification_status,
        sources=[s.SourceOut.model_validate(x) for x in sources_for(db, job.id, "university")],
    )


def professors_query(job_id: str):
    return (select(m.Professor).where(m.Professor.job_id == job_id)
            .order_by(m.Professor.sort_order, m.Professor.name))


def professor_detail(db: Session, p: m.Professor) -> s.ProfessorDetailOut:
    base = s.ProfessorOut.model_validate(p).model_dump()
    uni = db.get(m.University, p.university_id) if p.university_id else None
    return s.ProfessorDetailOut(
        **base, verification_checks=p.verification_checks or {}, notes=p.notes or [],
        sources=[s.SourceOut.model_validate(x) for x in sources_for(db, p.job_id, "professor", p.id)],
        university_name=uni.name if uni else None,
    )


def build_results(db: Session, job_id: str) -> dict:
    """Full structured result in the documented JSON shape."""
    job = db.get(m.ResearchJob, job_id)
    uni = university_payload(db, job)
    depts = db.scalars(select(m.Department).where(m.Department.job_id == job_id)
                       .order_by(m.Department.relevance_score.desc())).all()
    profs = db.scalars(professors_query(job_id)).all()
    return {
        "job_id": job_id,
        "fields": job.fields,
        "university": None if uni is None else {
            "name": uni.name, "name_chinese": uni.name_chinese, "official_url": uni.official_url,
            "country": uni.country, "location": uni.location,
            "verification_status": uni.verification_status,
            "sources": [x.source_url for x in uni.sources],
        },
        "departments": [s.DepartmentOut.model_validate(d).model_dump(mode="json") for d in depts],
        "professors": [
            {
                "id": p.id, "name": p.name, "name_chinese": p.name_chinese, "position": p.position,
                "department": p.department_name, "email": p.email or "Not publicly listed",
                "email_verified": p.email_verified, "profile_url": p.profile_url,
                "sources": [x.source_url for x in sources_for(db, job_id, "professor", p.id)],
                "verification_status": p.verification_status,
            }
            for p in profs
        ],
        "warnings": job.warnings,
    }
