"""Export endpoints: CSV, Excel, PDF."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app import models as m
from app.db import get_db
from app.services import exporter

router = APIRouter(prefix="/api/research", tags=["export"])

_TYPES = {
    "csv": ("text/csv; charset=utf-8", "csv", exporter.export_csv),
    "excel": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx", exporter.export_excel),
    "pdf": ("application/pdf", "pdf", exporter.export_pdf),
}


@router.get("/{job_id}/export/{fmt}", summary="Export results as csv | excel | pdf")
def export(job_id: str, fmt: str, db: Session = Depends(get_db)):
    if fmt not in _TYPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Format must be csv, excel or pdf.")
    job = db.get(m.ResearchJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Research job not found.")
    media, ext, fn = _TYPES[fmt]
    data = fn(db, job_id)
    uni = db.get(m.University, job.university_id) if job.university_id else None
    base = re.sub(r"[^A-Za-z0-9]+", "-", (uni.name if uni and uni.name else "research")).strip("-")[:60] or "research"
    return Response(content=data, media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{base}-{job_id}.{ext}"'})
