"""Pydantic schemas for structured LLM output. Every LLM response is validated against
one of these, and returned values are later grounding-checked against the source page."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UniversityExtraction(BaseModel):
    name_english: str | None = Field(None, description="Official English name if it appears in the text")
    name_chinese: str | None = Field(None, description="Official Chinese name if it appears in the text")
    city: str | None = Field(None, description="City (English) only if stated in the text")
    province: str | None = None
    country: str | None = None
    address_quote: str | None = Field(None, description="Verbatim address text from the source, if any")


class DepartmentChoice(BaseModel):
    index: int = Field(description="Index of the candidate link")
    name_english: str
    reason: str


class DepartmentSelection(BaseModel):
    departments: list[DepartmentChoice] = Field(default_factory=list)


class IndexSelection(BaseModel):
    indices: list[int] = Field(default_factory=list)


class ProfessorExtraction(BaseModel):
    is_individual_profile: bool = Field(description="True if this page is about ONE specific researcher")
    name_english: str | None = Field(None, description="English name ONLY if written on the page")
    name_chinese: str | None = Field(None, description="Chinese name exactly as written")
    position_english: str | None = None
    position_original: str | None = None
    emails: list[str] = Field(default_factory=list, description="Emails exactly as shown on the page")


class EmailDraftOut(BaseModel):
    subject: str
    body: str
