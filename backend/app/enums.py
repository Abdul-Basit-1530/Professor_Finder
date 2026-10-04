"""Shared status vocabularies.

NOT FOUND means "we looked and could not find it" — it never means the thing
does not exist (e.g. an email that is not published is not an email that is absent).
"""

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class Verification(StrEnum):
    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY VERIFIED"
    NOT_VERIFIED = "NOT VERIFIED"
    NOT_FOUND = "NOT FOUND"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmailStatus(StrEnum):
    VERIFIED = "VERIFIED EMAIL"
    NOT_FOUND = "EMAIL NOT FOUND"


class SourceType(StrEnum):
    OFFICIAL_PAGE = "official_page"
    OFFICIAL_PDF = "official_pdf"
    PROFILE_PAGE = "profile_page"
    FACULTY_LIST = "faculty_list"
    SEARCH_RESULT = "search_result"
    THIRD_PARTY = "third_party"
