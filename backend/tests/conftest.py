from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DATABASE_URL", "sqlite://")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ["LLM_PROVIDER"] = "none"
os.environ["ENVIRONMENT"] = "test"

from app.config import Settings  # noqa: E402
from app.db import Base, configure_engine  # noqa: E402


@pytest.fixture()
def db_url(tmp_path):
    url = f"sqlite:///{tmp_path / 'test.db'}"
    configure_engine(url)
    from app import db as dbmod
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=dbmod.engine)
    yield url
    Base.metadata.drop_all(bind=dbmod.engine)


@pytest.fixture()
def test_settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        llm_provider="none",
        openai_api_key=None,
        search_provider="none",
        request_delay_seconds=0,
        ssrf_protection=False,
        playwright_enabled=False,
        max_professors=20,
        max_departments=3,
        openalex_enabled=True,
        respect_robots_txt=True,
        environment="test",
    )
