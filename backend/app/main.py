"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api import exports, meta, professors, research
from app.config import get_settings
from app.db import init_db
from app.jobs import get_runner
from app.logging_config import configure_logging
from app.security import require_access

settings = get_settings()
configure_logging(settings.log_level)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.auto_create_tables:
        init_db()
    runner = get_runner()
    runner.recover()
    log.info("API started (env=%s, llm=%s, search=%s)", settings.environment,
             "on" if settings.llm_enabled else "off", settings.search_provider)
    yield
    runner.shutdown()


app = FastAPI(
    title="China University Professor Research Agent",
    version=__version__,
    description="Finds professors in relevant departments of official Chinese university websites — with their "
                "publicly listed email, profile link, sources and a verification status for every record.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Access-Token"],
    expose_headers=["Content-Disposition"],
)

protected = [Depends(require_access)]
app.include_router(meta.router)
app.include_router(research.router, dependencies=protected)
app.include_router(professors.router, dependencies=protected)
app.include_router(exports.router, dependencies=protected)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # pragma: no cover
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error."})
