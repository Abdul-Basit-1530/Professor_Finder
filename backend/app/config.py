"""Application configuration, loaded from environment variables / .env.

Every tunable that affects crawling, the LLM, or the research workflow lives here
so nothing important is hard-coded in the agents.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App -----------------------------------------------------------------
    app_name: str = "China University Professor Research Agent"
    environment: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:4200"
    # Optional shared access token. When set, every /api request (except health)
    # must send `X-Access-Token`. Keeps a public deployment from being abused.
    app_access_token: str | None = None
    max_jobs_per_hour_per_ip: int = 20

    # --- Database ------------------------------------------------------------
    database_url: str = "sqlite:///./research_agent.db"
    auto_create_tables: bool = True

    # --- LLM -----------------------------------------------------------------
    llm_provider: Literal["openai", "none"] = "openai"
    openai_api_key: str | None = None
    # Any OpenAI-compatible endpoint works (e.g. DeepSeek, Qwen/DashScope, Azure proxy).
    openai_base_url: str | None = None
    llm_model: str = "gpt-4.1-mini"
    llm_temperature: float = 0.0
    llm_timeout_seconds: float = 60.0
    llm_max_input_chars: int = 12000

    # --- Search --------------------------------------------------------------
    search_provider: Literal["none", "serper", "brave", "tavily", "searxng"] = "none"
    search_api_key: str | None = None
    searxng_url: str | None = None
    search_max_results: int = 8

    # --- Crawling ------------------------------------------------------------
    max_pages_per_job: int = 200
    request_delay_seconds: float = 1.0
    request_timeout_seconds: float = 20.0
    max_concurrent_requests: int = 4
    respect_robots_txt: bool = True
    user_agent: str = (
        "Mozilla/5.0 (compatible; CSCResearchAgent/1.0; +https://github.com/) "
        "academic-research-bot"
    )
    cache_ttl_hours: int = 72
    playwright_enabled: bool = False
    ssrf_protection: bool = True
    max_pdf_pages: int = 30

    # --- Research workflow ---------------------------------------------------
    max_professors: int = 40
    max_departments: int = 5
    max_faculty_list_pages: int = 4
    allow_non_institutional_emails: bool = False
    default_fields: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "Computer Science",
            "Artificial Intelligence",
            "Machine Learning",
            "Information Technology",
            "Software Engineering",
            "Data Science",
            "Computer Engineering",
            "Computer Networks",
            "Cybersecurity",
            "Internet of Things",
            "Cloud Computing",
            "Distributed Systems",
            "Natural Language Processing",
            "Computer Vision",
        ]
    )
    # Output language for user-facing text. Chinese originals are always preserved.
    output_language: Literal["en"] = "en"

    # --- Jobs ----------------------------------------------------------------
    max_concurrent_jobs: int = 2

    @field_validator("default_fields", mode="before")
    @classmethod
    def _split_fields(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider == "openai" and bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
