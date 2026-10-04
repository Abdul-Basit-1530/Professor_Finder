"""Health and configuration metadata."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app import __version__, db
from app.config import get_settings
from app.services.fields import resolve_fields

router = APIRouter(tags=["meta"])


@router.get("/api/health")
def health():
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "version": __version__}


@router.get("/api/meta/config")
def public_config():
    s = get_settings()
    return {
        "default_fields": [f.to_dict() for f in resolve_fields(s.default_fields)],
        "llm_enabled": s.llm_enabled,
        "llm_model": s.llm_model if s.llm_enabled else None,
        "search_provider": s.search_provider,
        "max_professors": s.max_professors,
        "access_token_required": bool(s.app_access_token),
    }
