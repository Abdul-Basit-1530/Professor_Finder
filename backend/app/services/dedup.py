"""Professor de-duplication.

The same person can appear on the Chinese and English faculty pages, the department
page and a lab page. Records are merged when any strong identifier matches:
email, profile URL, Chinese name (within the same university), or an
order-insensitive English name key within the same department.
"""

from __future__ import annotations

from app.agents.context import ProfessorInfo
from app.services.text_utils import name_key
from app.services.url_utils import canonical_key


def _keys(p: ProfessorInfo) -> list[str]:
    keys = []
    if p.email:
        keys.append("e:" + p.email.lower())
    if p.profile_url:
        keys.append("u:" + canonical_key(p.profile_url))
    if p.name_chinese:
        keys.append("zh:" + p.name_chinese)
    nk = name_key(p.name)
    if nk and not p.name_chinese:
        dept = (p.department_name or "").lower()
        keys.append(f"n:{nk}|{dept}")
    return keys


def _merge(a: ProfessorInfo, b: ProfessorInfo) -> ProfessorInfo:
    # Prefer the record with a loaded profile page as the base.
    base, other = (a, b) if (a.profile_ok or not b.profile_ok) else (b, a)
    for attr in ("name_chinese", "position", "position_original", "email", "school", "department_name"):
        if not getattr(base, attr) and getattr(other, attr):
            setattr(base, attr, getattr(other, attr))
    if base.name_is_romanized and other.name and not other.name_is_romanized and other.name != other.name_chinese:
        base.name, base.name_is_romanized = other.name, False
    base.email_verified = base.email_verified or other.email_verified
    urls = {(s.url, s.supports) for s in base.sources}
    base.sources += [s for s in other.sources if (s.url, s.supports) not in urls]
    if other.profile_text and other.profile_text not in base.profile_text:
        base.profile_text += "\n" + other.profile_text
    base.profile_mailtos = list({*base.profile_mailtos, *other.profile_mailtos})
    base.profile_ok = base.profile_ok or other.profile_ok
    base.notes = list(dict.fromkeys(base.notes + other.notes))
    return base


def deduplicate(profs: list[ProfessorInfo]) -> list[ProfessorInfo]:
    """Transitive merge: if a new record links two existing ones (e.g. Chinese name matches
    one, email matches another), all three collapse into a single professor."""
    result: list[ProfessorInfo] = []
    for p in profs:
        keys = set(_keys(p))
        hits = [i for i, r in enumerate(result) if keys & set(_keys(r))]
        if not hits:
            result.append(p)
            continue
        merged = p
        for i in hits:
            merged = _merge(result[i], merged)
        for i in reversed(hits):
            result.pop(i)
        result.insert(hits[0], merged)
    return result
