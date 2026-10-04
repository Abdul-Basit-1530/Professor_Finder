"""Research job endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import schemas as s
from app.agents.orchestrator import initial_steps
from app.config import get_settings
from app.db import get_db
from app.enums import JobStatus
from app.jobs import get_runner
from app.security import client_ip, job_limiter
from app.services.results import build_results, professors_query, university_payload

router = APIRouter(prefix="/api/research", tags=["research"])


def _job_or_404(db: Session, job_id: str) -> m.ResearchJob:
    job = db.get(m.ResearchJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research job not found.")
    return job


def job_out(db: Session, job: m.ResearchJob) -> s.JobOut:
    uni = db.get(m.University, job.university_id) if job.university_id else None
    return s.JobOut(
        id=job.id, university_url=job.university_url, university_name=uni.name if uni else None,
        fields=job.fields or [], options=job.options or {}, status=job.status, progress=job.progress,
        current_step=job.current_step, steps=[s.StepOut(**x) for x in (job.steps or [])],
        warnings=job.warnings or [], stats=job.stats or {}, error_message=job.error_message,
        created_at=job.created_at, started_at=job.started_at, completed_at=job.completed_at)


@router.post("/start", response_model=s.ResearchStartResponse, status_code=status.HTTP_202_ACCEPTED,
             summary="Start a research job")
def start_research(body: s.ResearchStartRequest, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()
    ip = client_ip(request)
    job_limiter.check(ip, settings.max_jobs_per_hour_per_ip)
    fields = body.fields + [f for f in body.custom_fields if f not in body.fields]
    if not fields:
        fields = list(settings.default_fields)
    job = m.ResearchJob(
        id=uuid.uuid4().hex[:16], university_url=body.university_url, fields=fields,
        options={"max_professors": body.max_professors or settings.max_professors,
                 "force_refresh": body.force_refresh},
        status=JobStatus.QUEUED.value, progress=0, steps=initial_steps(), current_step="Queued",
        warnings=[], stats={}, requester_ip=ip)
    db.add(job)
    db.commit()
    get_runner().submit(job.id)
    return s.ResearchStartResponse(job_id=job.id, status=job.status)


@router.get("", response_model=list[s.JobOut], summary="List recent research jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    jobs = db.scalars(select(m.ResearchJob).order_by(m.ResearchJob.created_at.desc()).limit(limit)).all()
    return [job_out(db, j) for j in jobs]


@router.get("/{job_id}", response_model=s.JobOut, summary="Job status and progress")
def get_job(job_id: str, db: Session = Depends(get_db)):
    return job_out(db, _job_or_404(db, job_id))


@router.post("/{job_id}/cancel", response_model=s.JobOut)
def cancel_job(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    if job.status in (JobStatus.QUEUED.value, JobStatus.RUNNING.value):
        job.cancel_requested = True
        if job.status == JobStatus.QUEUED.value:
            job.status = JobStatus.CANCELLED.value
        db.commit()
    return job_out(db, job)


@router.get("/{job_id}/university", response_model=s.UniversityOut | None)
def get_university(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    return university_payload(db, job)


@router.get("/{job_id}/departments", response_model=list[s.DepartmentOut])
def get_departments(job_id: str, db: Session = Depends(get_db)):
    _job_or_404(db, job_id)
    return db.scalars(select(m.Department).where(m.Department.job_id == job_id)
                      .order_by(m.Department.relevance_score.desc())).all()


@router.get("/{job_id}/professors", response_model=list[s.ProfessorOut])
def get_professors(
    job_id: str,
    department: str | None = None,
    verification: str | None = Query(None, description="VERIFIED | PARTIALLY VERIFIED | NOT VERIFIED"),
    has_email: bool | None = None,
    q: str | None = Query(None, description="Search name, email or department"),
    sort: str = Query("default", pattern="^(default|name|department)$"),
    db: Session = Depends(get_db),
):
    _job_or_404(db, job_id)
    profs = [s.ProfessorOut.model_validate(p) for p in db.scalars(professors_query(job_id)).all()]
    if department:
        profs = [p for p in profs if (p.department_name or "") == department]
    if verification:
        profs = [p for p in profs if p.verification_status == verification]
    if has_email is not None:
        profs = [p for p in profs if bool(p.email) == has_email]
    if q:
        needle = q.lower()
        profs = [p for p in profs if needle in " ".join(
            [p.name, p.name_chinese or "", p.email or "", p.department_name or ""]).lower()]
    if sort == "name":
        profs.sort(key=lambda p: p.name.lower())
    elif sort == "department":
        profs.sort(key=lambda p: (p.department_name or "").lower())
    return profs


@router.get("/{job_id}/results", summary="Full structured result (JSON)")
def get_results(job_id: str, db: Session = Depends(get_db)):
    job = _job_or_404(db, job_id)
    row = db.scalar(select(m.ResearchResult).where(m.ResearchResult.job_id == job_id))
    if row is not None:
        return row.summary
    return build_results(db, job.id)
