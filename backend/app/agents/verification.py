"""Verification Agent — data-quality checks and final verification status per professor.

Checks
  name_found              name (Chinese or English) appears on the profile page
  university_association  profile/listing page is on the official university domain
  profile_url_valid       profile page loaded successfully (HTTP 2xx)
  email_public            email literally present on the profile page
  email_institutional     email domain is the university's or an academic domain

Status
  VERIFIED            name + association + valid profile + public email
  PARTIALLY VERIFIED  name + association + valid profile (no public email)
  NOT VERIFIED        otherwise
"""

from __future__ import annotations

from app.agents.context import ProfessorInfo, ResearchContext
from app.enums import EmailStatus, Verification
from app.services.text_utils import (
    email_appears_in,
    is_grounded,
    is_institutional_email,
)


def verify_professor(ctx: ResearchContext, p: ProfessorInfo) -> None:
    text = p.profile_text
    name_found = bool(text) and bool(
        (p.name_chinese and is_grounded(p.name_chinese, text))
        or (not p.name_is_romanized and is_grounded(p.name, text))
    )
    association = bool(
        (p.profile_url and ctx.official(p.profile_url)) or (p.listing_url and ctx.official(p.listing_url))
    )
    email_public = bool(p.email and text and email_appears_in(p.email, text, p.profile_mailtos))
    if p.email and not email_public:
        # Defensive: an email we cannot re-find on the page is dropped, never shown as fact.
        p.notes.append("Email could not be re-verified on the profile page and was removed.")
        p.email = None
    p.email_verified = email_public
    institutional = bool(p.email and is_institutional_email(p.email, ctx.domain))

    p.verification_checks = {
        "name_found": name_found,
        "university_association": association,
        "profile_url_valid": p.profile_ok,
        "email_public": email_public,
        "email_institutional": institutional,
        "romanized_name": p.name_is_romanized,
    }
    if name_found and association and p.profile_ok and email_public:
        p.verification_status = Verification.VERIFIED.value
    elif name_found and association and p.profile_ok:
        p.verification_status = Verification.PARTIALLY_VERIFIED.value
    else:
        p.verification_status = Verification.NOT_VERIFIED.value


def verify_all(ctx: ResearchContext, profs: list[ProfessorInfo]) -> dict:
    counts = {v.value: 0 for v in (Verification.VERIFIED, Verification.PARTIALLY_VERIFIED, Verification.NOT_VERIFIED)}
    for p in profs:
        verify_professor(ctx, p)
        counts[p.verification_status] += 1
    order = {Verification.VERIFIED.value: 0, Verification.PARTIALLY_VERIFIED.value: 1}
    profs.sort(key=lambda p: (order.get(p.verification_status, 2), not p.email))
    ctx.note("Verification: " + ", ".join(f"{k}: {v}" for k, v in counts.items()))
    return counts


def email_status(p: ProfessorInfo) -> str:
    return EmailStatus.VERIFIED.value if p.email_verified else EmailStatus.NOT_FOUND.value
