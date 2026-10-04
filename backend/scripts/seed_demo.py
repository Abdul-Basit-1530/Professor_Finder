"""Seed the configured database with a demo research job (offline).

Runs the real research pipeline against the bundled mock university website
(tests/mock_site.py), so the UI can be explored without crawling a live site:

    python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import uuid

from app import models as m
from app.agents.orchestrator import Orchestrator, initial_steps
from app.config import get_settings
from app.db import SessionLocal, init_db
from app.logging_config import configure_logging
from tests.mock_site import ROOT, site_transport

FIELDS = ["Artificial Intelligence", "Natural Language Processing", "Machine Learning", "Computer Vision",
          "Software Engineering", "Distributed Systems", "Cloud Computing"]


def main() -> None:
    configure_logging("INFO")
    init_db()
    settings = get_settings().model_copy(update={"request_delay_seconds": 0, "ssrf_protection": False})
    job_id = uuid.uuid4().hex[:16]
    with SessionLocal() as db:
        db.add(m.ResearchJob(id=job_id, university_url=ROOT + "/", fields=FIELDS,
                             options={"max_professors": 20, "force_refresh": True},
                             status="queued", steps=initial_steps(), warnings=[], stats={}))
        db.commit()
    asyncio.run(Orchestrator(job_id, settings=settings, transport=site_transport()).run())
    print(f"\nDemo job created: {job_id}\nOpen http://localhost:4200/research/{job_id}/overview")


if __name__ == "__main__":
    main()
