"""University Research Agent — central workflow orchestrating the specialised agents.

    University Discovery → Departments → Professor Discovery → Verification → Results

Each step reports progress to the job row. A step failure is recorded and the
workflow continues where possible; only an unreachable/blocked university site
(or an explicit cancel) stops the job.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from app import models as m
from app.agents import persistence as store
from app.agents.context import ResearchContext
from app.agents.departments import discover_departments
from app.agents.professors import discover_professors
from app.agents.university import FatalResearchError, discover_university
from app.agents.verification import verify_all
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.enums import JobStatus, StepStatus
from app.services.dedup import deduplicate
from app.services.fetcher import Fetcher
from app.services.fields import resolve_fields
from app.services.llm import LLMProvider, build_llm
from app.services.results import build_results
from app.services.search import SearchProvider, build_search
from app.services.url_utils import registrable_domain

log = logging.getLogger("agent.orchestrator")

STEPS: list[tuple[str, str, int]] = [
    ("university", "University identified", 10),
    ("departments", "Relevant departments found", 20),
    ("professors", "Finding professors", 55),
    ("verification", "Verifying emails & profiles", 10),
    ("results", "Generating results", 5),
]


def initial_steps() -> list[dict]:
    return [{"key": k, "label": label, "status": StepStatus.PENDING.value, "message": None,
             "started_at": None, "finished_at": None} for k, label, _ in STEPS]


class JobCancelled(Exception):
    pass


class Orchestrator:
    def __init__(self, job_id: str, *, settings: Settings | None = None, llm: LLMProvider | None = None,
                 search: SearchProvider | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.job_id = job_id
        self.settings = settings or get_settings()
        self._llm = llm
        self._search = search
        self._transport = transport
        self._last_flush = 0.0

    # ---------------------------------------------------------------- job row helpers
    def _update(self, **fields) -> m.ResearchJob:
        with SessionLocal() as db:
            job = db.get(m.ResearchJob, self.job_id)
            for k, v in fields.items():
                setattr(job, k, v)
            db.commit()
            return job

    def _job(self) -> m.ResearchJob:
        with SessionLocal() as db:
            return db.get(m.ResearchJob, self.job_id)

    def _set_step(self, key: str, status: str, message: str | None = None, progress: int | None = None) -> None:
        with SessionLocal() as db:
            job = db.get(m.ResearchJob, self.job_id)
            steps = [dict(s) for s in (job.steps or initial_steps())]
            now = datetime.now(timezone.utc).isoformat()
            for s in steps:
                if s["key"] == key:
                    s["status"] = status
                    if message is not None:
                        s["message"] = message[:300]
                    if status == StepStatus.RUNNING.value and not s.get("started_at"):
                        s["started_at"] = now
                    if status in (StepStatus.DONE.value, StepStatus.FAILED.value, StepStatus.SKIPPED.value):
                        s["finished_at"] = now
                    if status == StepStatus.RUNNING.value:
                        job.current_step = s["label"] + "…"
            job.steps = steps
            if progress is not None:
                job.progress = progress
            if self.ctx:
                job.warnings = list(self.ctx.warnings)[:50]
            if job.cancel_requested:
                db.commit()
                raise JobCancelled()
            db.commit()

    def _progress_message(self, key: str):
        def cb(msg: str) -> None:
            now = time.monotonic()
            if now - self._last_flush < 0.75:
                return
            self._last_flush = now
            try:
                self._set_step(key, StepStatus.RUNNING.value, msg)
            except JobCancelled:
                raise
            except Exception:  # progress updates are best-effort
                log.debug("progress update failed", exc_info=True)
        return cb

    # ---------------------------------------------------------------- run
    ctx: ResearchContext | None = None

    async def run(self) -> None:
        job = self._job()
        if job is None:
            log.error("Job %s not found", self.job_id)
            return
        opts = job.options or {}
        fields = resolve_fields(job.fields or self.settings.default_fields)
        settings = self.settings
        fetcher = Fetcher(settings, session_factory=SessionLocal, transport=self._transport,
                          force_refresh=bool(opts.get("force_refresh")),
                          max_pages=opts.get("max_pages") or settings.max_pages_per_job)
        self.ctx = ctx = ResearchContext(
            job_id=self.job_id, start_url=job.university_url, domain=registrable_domain(job.university_url),
            fields=fields, settings=settings, fetcher=fetcher, llm=self._llm or build_llm(settings),
            search=self._search or build_search(settings),
            max_professors=int(opts.get("max_professors") or settings.max_professors),
        )
        log.info("Research job %s started for %s (fields: %s, llm: %s)", self.job_id, job.university_url,
                 ", ".join(f.label for f in fields), ctx.llm.name)
        self._update(status=JobStatus.RUNNING.value, started_at=datetime.now(timezone.utc), progress=1,
                     steps=job.steps or initial_steps(), current_step="Starting…")
        if not ctx.llm.available:
            ctx.warn("No LLM configured — running in heuristic-only mode (lower recall, same verification rules).")

        progress = 1
        profs = []
        failed: set[str] = set()
        try:
            for key, label, weight in STEPS:
                ctx.on_progress = self._progress_message(key)
                self._set_step(key, StepStatus.RUNNING.value, None, progress)
                if key == "verification" and "professors" in failed:
                    self._set_step(key, StepStatus.SKIPPED.value, "Skipped: professor discovery failed")
                    progress += weight
                    continue
                try:
                    msg = await self._run_step(key, ctx, profs)
                    if key == "professors":
                        profs = msg[1]
                        msg = msg[0]
                    progress += weight
                    self._set_step(key, StepStatus.DONE.value, msg, min(progress, 99))
                except (FatalResearchError, JobCancelled):
                    raise
                except Exception as exc:
                    log.exception("Step %s failed in job %s", key, self.job_id)
                    failed.add(key)
                    ctx.warn(f"Step '{label}' failed: {type(exc).__name__}: {str(exc)[:200]}")
                    progress += weight
                    self._set_step(key, StepStatus.FAILED.value, f"Failed: {str(exc)[:200]}", min(progress, 99))
            stats = {**(self._job().stats or {}), "pages_fetched": fetcher.network_fetches,
                     "cache_hits": fetcher.cache_hits, "fetch_errors": fetcher.errors,
                     "llm": ctx.llm.name, "professors": len(profs)}
            self._update(status=JobStatus.COMPLETED.value, progress=100, current_step="Completed",
                         completed_at=datetime.now(timezone.utc), warnings=ctx.warnings[:50], stats=stats)
            log.info("Research job %s completed: %d professors, %d pages fetched", self.job_id, len(profs),
                     fetcher.network_fetches)
        except JobCancelled:
            self._update(status=JobStatus.CANCELLED.value, current_step="Cancelled",
                         completed_at=datetime.now(timezone.utc))
            log.info("Research job %s cancelled", self.job_id)
        except FatalResearchError as exc:
            self._mark_running_failed(str(exc))
            self._update(status=JobStatus.FAILED.value, error_message=str(exc), current_step="Failed",
                         completed_at=datetime.now(timezone.utc), warnings=ctx.warnings[:50])
            log.warning("Research job %s failed: %s", self.job_id, exc)
        except Exception as exc:  # pragma: no cover - last-resort guard
            log.exception("Research job %s crashed", self.job_id)
            self._update(status=JobStatus.FAILED.value, error_message=f"Internal error: {type(exc).__name__}",
                         current_step="Failed", completed_at=datetime.now(timezone.utc))
        finally:
            await fetcher.aclose()

    def _mark_running_failed(self, msg: str) -> None:
        with SessionLocal() as db:
            job = db.get(m.ResearchJob, self.job_id)
            steps = [dict(s) for s in job.steps or []]
            for s in steps:
                if s["status"] == StepStatus.RUNNING.value:
                    s["status"] = StepStatus.FAILED.value
                    s["message"] = msg[:300]
                elif s["status"] == StepStatus.PENDING.value:
                    s["status"] = StepStatus.SKIPPED.value
            job.steps = steps
            db.commit()

    async def _run_step(self, key: str, ctx: ResearchContext, profs: list):
        if key == "university":
            info = await discover_university(ctx)
            with SessionLocal() as db:
                store.save_university(db, ctx, info)
            return f"{info.name}" + (f" ({info.name_chinese})" if info.name_chinese and info.name_chinese != info.name else "")
        if key == "departments":
            depts = await discover_departments(ctx)
            with SessionLocal() as db:
                store.save_departments(db, ctx, depts)
            return f"{len(depts)} relevant schools/departments"
        if key == "professors":
            found = deduplicate(await discover_professors(ctx))
            ctx.professors = found
            with SessionLocal() as db:
                store.save_professors(db, ctx, found)
            return f"{len(found)} professors discovered", found
        if key == "verification":
            counts = verify_all(ctx, profs)
            with SessionLocal() as db:
                store.save_professors(db, ctx, profs)
            with_email = sum(1 for p in profs if p.email)
            return f"{with_email} of {len(profs)} with a public email · " + ", ".join(
                f"{v} {k.lower()}" for k, v in counts.items())
        if key == "results":
            with SessionLocal() as db:
                summary = build_results(db, self.job_id)
                existing = db.query(m.ResearchResult).filter_by(job_id=self.job_id).one_or_none()
                if existing:
                    existing.summary = summary
                else:
                    db.add(m.ResearchResult(job_id=self.job_id, summary=summary))
                db.commit()
            return "Results ready"
        raise ValueError(key)
