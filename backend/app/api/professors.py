"""Professor endpoints, including personalised email draft generation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import schemas as s
from app.agents.email_writer import generate_email
from app.config import get_settings
from app.db import get_db
from app.services.llm import build_llm
from app.services.results import professor_detail

router = APIRouter(prefix="/api/professors", tags=["professors"])


def _prof_or_404(db: Session, prof_id: int) -> m.Professor:
    p = db.get(m.Professor, prof_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Professor not found.")
    return p


@router.get("/{prof_id}", response_model=s.ProfessorDetailOut)
def get_professor(prof_id: int, db: Session = Depends(get_db)):
    return professor_detail(db, _prof_or_404(db, prof_id))


@router.post("/{prof_id}/generate-email", response_model=s.EmailDraftResponse,
             summary="Generate an editable supervision-request email draft (never sent)")
async def generate(prof_id: int, body: s.EmailRequest, db: Session = Depends(get_db)):
    p = _prof_or_404(db, prof_id)
    subject, text, by, warnings = await generate_email(build_llm(get_settings()), p, body)
    draft = m.EmailDraft(professor_id=p.id, subject=subject, body=text, generated_by=by, warnings=warnings,
                         student_profile=body.model_dump())
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


@router.get("/{prof_id}/email-drafts", response_model=list[s.EmailDraftResponse])
def list_drafts(prof_id: int, db: Session = Depends(get_db)):
    _prof_or_404(db, prof_id)
    return db.scalars(select(m.EmailDraft).where(m.EmailDraft.professor_id == prof_id)
                      .order_by(m.EmailDraft.created_at.desc()).limit(10)).all()
