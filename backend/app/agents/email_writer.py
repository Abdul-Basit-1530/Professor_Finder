"""Supervision-request email generator.

The draft uses only the professor's verified contact facts (name, position,
department, university). It never claims anything about the professor's research,
because research is not collected — the student should add that after reading the
profile. Drafts are returned for the student to edit — nothing is sent.
"""

from __future__ import annotations

import json

from app import models as m
from app.agents.schemas import EmailDraftOut
from app.schemas import EmailRequest
from app.services.llm import LLMProvider


def _facts(p: m.Professor) -> dict:
    return {"name": p.name, "name_chinese": p.name_chinese, "position": p.position,
            "department": p.department_name, "profile_url": p.profile_url}


def _warnings(p: m.Professor) -> list[str]:
    warnings = ["Read the professor's profile and add a sentence about their specific work before sending."]
    if not p.email:
        warnings.append("No publicly listed email was found for this professor.")
    return warnings


def _salutation(p: m.Professor) -> str:
    if not p.name:
        return "Dear Professor,"
    if any("一" <= c <= "鿿" for c in p.name):
        return f"Dear Professor {p.name},"
    tokens = p.name.split()
    upper = [t for t in tokens if len(t) > 1 and t.isupper()]  # "ZHANG Wei" style marks the surname
    surname = upper[0].capitalize() if upper else (tokens[0] if p.name_is_romanized else tokens[-1])
    return f"Dear Professor {surname},"


def template_email(p: m.Professor, req: EmailRequest) -> tuple[str, str]:
    subject = f"Prospective {req.target_degree} student ({req.scholarship}) — interest in {req.research_interest}"
    dept = f" in the {p.department_name}" if p.department_name else ""
    lines = [_salutation(p), ""]
    lines.append(f"My name is {req.student_name}, and I am applying for a {req.target_degree} program "
                 f"under the {req.scholarship}. I am writing to ask whether you would consider supervising me{dept}.")
    lines.append("")
    lines.append(f"My research interest is {req.research_interest}, and I would be glad to learn whether my "
                 "background could fit your group.")
    lines += ["", "About my background:", req.student_background.strip(), ""]
    if req.extra_notes:
        lines += [req.extra_notes.strip(), ""]
    lines.append("If you are accepting students, I would be grateful for the opportunity to apply under your "
                 "supervision, and for a pre-acceptance letter if your process allows it. I have attached my CV "
                 "and transcripts for your review.")
    lines += ["", "Thank you for your time and consideration.", "", "Kind regards,", req.student_name]
    return subject, "\n".join(lines)


async def generate_email(llm: LLMProvider, p: m.Professor, req: EmailRequest) -> tuple[str, str, str, list[str]]:
    warnings = _warnings(p)
    if llm.available:
        content = json.dumps({"professor": _facts(p), "student": req.model_dump()}, ensure_ascii=False, indent=2)
        out = await llm.extract(
            "supervision_email",
            "Write a concise, professional email (150-250 words) from the student to the professor asking about "
            f"{req.target_degree} supervision and an acceptance/pre-admission letter for the {req.scholarship}. "
            f"Tone: {req.tone}. Use ONLY the facts provided. Do NOT claim anything about the professor's research "
            "or publications (none are provided). Do not invent student achievements. End with the student's "
            "name. Mention that a CV is attached.",
            content, EmailDraftOut)
        if out and out.body.strip():
            return out.subject.strip(), out.body.strip(), "llm", warnings
    subject, body = template_email(p, req)
    return subject, body, "template", warnings
