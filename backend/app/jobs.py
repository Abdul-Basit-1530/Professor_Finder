"""Research job runner.

Jobs are persisted in `research_jobs`; the runner executes them on a bounded
thread pool, each with its own asyncio event loop, so long crawls never block the
API. On startup, jobs left `running` by a previous process are marked failed and
`queued` jobs are resumed. Swapping this for Celery/RQ/Arq later only requires
replacing `JobRunner.submit`.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select

from app import models as m
from app.config import get_settings
from app.db import SessionLocal
from app.enums import JobStatus

log = logging.getLogger("agent.jobs")


def _run_sync(job_id: str) -> None:
    from app.agents.orchestrator import Orchestrator

    try:
        asyncio.run(Orchestrator(job_id).run())
    except Exception:  # pragma: no cover
        log.exception("Job %s crashed in runner", job_id)


class JobRunner:
    def __init__(self, max_workers: int | None = None) -> None:
        self._pool = ThreadPoolExecutor(max_workers=max_workers or get_settings().max_concurrent_jobs,
                                        thread_name_prefix="research-job")

    def submit(self, job_id: str) -> None:
        log.info("Queued research job %s", job_id)
        self._pool.submit(_run_sync, job_id)

    def recover(self) -> None:
        with SessionLocal() as db:
            stale = db.scalars(select(m.ResearchJob).where(m.ResearchJob.status == JobStatus.RUNNING.value)).all()
            for job in stale:
                job.status = JobStatus.FAILED.value
                job.error_message = "Interrupted by a server restart. Please start the research again."
                job.completed_at = datetime.now(timezone.utc)
            queued = db.scalars(select(m.ResearchJob.id).where(m.ResearchJob.status == JobStatus.QUEUED.value)).all()
            db.commit()
        for jid in queued:
            self.submit(jid)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)


runner: JobRunner | None = None


def get_runner() -> JobRunner:
    global runner
    if runner is None:
        runner = JobRunner()
    return runner
