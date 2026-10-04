"""Shared state passed between agents during one research job."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import Settings
from app.enums import SourceType, Verification
from app.services.fetcher import Fetcher, Page
from app.services.fields import FieldSpec
from app.services.llm import LLMProvider
from app.services.search import SearchProvider
from app.services.url_utils import is_official

log = logging.getLogger("agent")


@dataclass
class SourceRef:
    url: str
    source_type: str
    title: str | None = None
    supports: str | None = None
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_page(cls, page: Page, supports: str, domain: str, kind: str | None = None) -> "SourceRef":
        if kind is None:
            if is_official(page.final_url, domain):
                kind = SourceType.OFFICIAL_PDF.value if page.is_pdf else SourceType.OFFICIAL_PAGE.value
            else:
                kind = SourceType.THIRD_PARTY.value
        return cls(url=page.final_url, source_type=kind, title=(page.title or None) and page.title[:500],
                   supports=supports, retrieved_at=page.fetched_at)


@dataclass
class UniversityInfo:
    official_url: str
    domain: str
    name: str | None = None
    name_chinese: str | None = None
    country: str | None = None
    location: str | None = None
    verification_status: str = Verification.NOT_VERIFIED.value
    sources: list[SourceRef] = field(default_factory=list)
    db_id: int | None = None


@dataclass
class DepartmentInfo:
    name: str
    url: str | None
    name_chinese: str | None = None
    school: str | None = None
    faculty_list_urls: list[str] = field(default_factory=list)
    matched_fields: list[str] = field(default_factory=list)
    relevance_score: float = 0.0
    verification_status: str = Verification.NOT_VERIFIED.value
    sources: list[SourceRef] = field(default_factory=list)
    db_id: int | None = None


@dataclass
class ProfessorInfo:
    name: str
    name_chinese: str | None = None
    name_is_romanized: bool = False
    position: str | None = None
    position_original: str | None = None
    department_name: str | None = None
    department: DepartmentInfo | None = None
    school: str | None = None
    email: str | None = None
    email_verified: bool = False
    profile_url: str | None = None
    profile_text: str = ""  # not persisted; used by verification
    profile_mailtos: list[str] = field(default_factory=list)
    listing_url: str | None = None
    verification_status: str = Verification.NOT_VERIFIED.value
    verification_checks: dict[str, Any] = field(default_factory=dict)
    sources: list[SourceRef] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    profile_ok: bool = False
    db_id: int | None = None


@dataclass
class ResearchContext:
    job_id: str
    start_url: str
    domain: str
    fields: list[FieldSpec]
    settings: Settings
    fetcher: Fetcher
    llm: LLMProvider
    search: SearchProvider
    max_professors: int = 40
    homepage: Page | None = None
    english_homepage: Page | None = None
    pages: dict[str, Page] = field(default_factory=dict)
    university: UniversityInfo | None = None
    departments: list[DepartmentInfo] = field(default_factory=list)
    professors: list[ProfessorInfo] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    on_progress: Callable[[str], None] | None = None

    def warn(self, msg: str) -> None:
        log.warning("[job %s] %s", self.job_id, msg)
        if msg not in self.warnings:
            self.warnings.append(msg)

    def note(self, msg: str) -> None:
        log.info("[job %s] %s", self.job_id, msg)
        if self.on_progress:
            self.on_progress(msg)

    async def fetch(self, url: str) -> Page:
        page = await self.fetcher.fetch(url)
        if page.ok:
            self.pages[page.final_url] = page
        return page

    def official(self, url: str) -> bool:
        return is_official(url, self.domain)

    def all_links(self):
        """Every link seen on fetched official pages (deduplicated by URL)."""
        seen = {}
        for p in list(self.pages.values()):
            for ln in p.links:
                if ln.url not in seen and self.official(ln.url):
                    seen[ln.url] = ln
        return list(seen.values())
