"""Professor Discovery Agent — University → School → Department → Faculty list → Profile.

Discovery walks official faculty directories rather than relying on web search.
For every professor we collect only what a student needs to make contact:
name (English / Chinese), position, department, public institutional email and
profile URL. Every value is grounded in the profile page:
* emails must literally appear on the page (or in an explicit obfuscated form)
* English names are taken from the page, or romanised only when unambiguous
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from app.agents.context import DepartmentInfo, ProfessorInfo, ResearchContext, SourceRef
from app.agents.schemas import IndexSelection, ProfessorExtraction
from app.enums import SourceType
from app.services.fetcher import Page
from app.services.link_classifier import pagination_links, top_links
from app.services.llm import truncate_for_llm
from app.services.text_utils import (
    clean_person_text,
    detect_position,
    extract_emails,
    has_cjk,
    is_grounded,
    is_institutional_email,
    looks_like_chinese_name,
    looks_like_english_name,
    romanize_chinese_name,
    strip_honorific,
)
from app.services.url_utils import canonical_key, hostname

GENERIC_LOCALPARTS = re.compile(
    r"^(?:office|admin|webmaster|web|info|contact|service|support|yjs|yjsy|zsb|zs|jwc|gs|grad|"
    r"international|intl|iso|admission|admissions|recruit|hr|rsc|xb|dean|news|cs|cse|school|college|"
    r"dept|department|lab|postmaster|noreply|no-reply)\d*$", re.I)
FACULTY_PAGE = re.compile(r"师资|教师|导师|教授|名录|faculty|people|staff|teacher|szdw|jsml|dsdw|researchers|"
                          r"专任|队伍|人才|研究员|members", re.I)
_NEWS_TITLE = re.compile(r"新闻|公告|通知|报道|发表|举行|召开|举办|喜报|讲座|会议|动态|news|event", re.I)
EMAIL_LABEL = re.compile(r"邮箱|电子邮件|电邮|E-?mail", re.I)
POSITION_CONTEXT = re.compile(r"教授|副教授|讲师|研究员|Professor|Lecturer|Researcher|博导|硕导", re.I)


@dataclass
class Candidate:
    name_text: str
    url: str
    department: DepartmentInfo
    listing: Page
    context: str
    priority: float


def _person_links(ctx: ResearchContext, page: Page) -> list[tuple[str, str, str]]:
    out = []
    for ln in page.links:
        name = clean_person_text(ln.text)
        if not (looks_like_chinese_name(name) or looks_like_english_name(name)):
            continue
        if not ctx.official(ln.url) or canonical_key(ln.url) == canonical_key(page.final_url):
            continue
        out.append((name, ln.url, ln.context))
    return out


async def _llm_pick_people(ctx: ResearchContext, page: Page) -> list[tuple[str, str, str]]:
    links = [ln for ln in page.links if ctx.official(ln.url) and 1 < len(ln.text) <= 30][:150]
    if not links:
        return []
    listing = "\n".join(f"[{i}] {ln.text}" for i, ln in enumerate(links))
    out = await ctx.llm.extract(
        "faculty_link_selection",
        "This is the list of links on a university faculty-directory page. Return the indices of links whose "
        "text is the name of an individual faculty member/researcher (links to their personal profile).",
        listing, IndexSelection)
    if not out:
        return []
    return [(clean_person_text(links[i].text), links[i].url, links[i].context)
            for i in out.indices if 0 <= i < len(links)]


async def _collect_candidates(ctx: ResearchContext) -> list[Candidate]:
    cands: dict[str, Candidate] = {}
    for dept in ctx.departments:
        queue = list(dept.faculty_list_urls) or ([dept.url] if dept.url else [])
        visited: set[str] = set()
        budget = ctx.settings.max_faculty_list_pages + 3
        while queue and budget > 0:
            url = queue.pop(0)
            if canonical_key(url) in visited:
                continue
            visited.add(canonical_key(url))
            budget -= 1
            page = await ctx.fetch(url)
            if not page.ok:
                ctx.warn(f"Faculty list unavailable: {url} ({page.error})")
                continue
            if _NEWS_TITLE.search(page.title) and not FACULTY_PAGE.search(page.title + " " + page.final_url):
                continue  # a news article, not a faculty directory
            people = _person_links(ctx, page)
            listing_like = bool(FACULTY_PAGE.search(page.title + " " + page.final_url))
            if not people and listing_like and ctx.settings.playwright_enabled:
                rendered = await ctx.fetcher.render(page.final_url)  # names injected by JavaScript
                if rendered is not None:
                    ctx.pages[rendered.final_url] = rendered
                    page = rendered
                    people = _person_links(ctx, page)
            if len(people) < 3 and not listing_like:
                people = []  # a stray name-like link on a non-directory page is not evidence of a professor
            if len(people) < 3 and ctx.llm.available and listing_like:
                people = people + [p for p in await _llm_pick_people(ctx, page) if p[1] not in {x[1] for x in people}]
            ctx.note(f"{len(people)} people listed on {page.title or url}")
            for name, purl, context in people:
                key = canonical_key(purl)
                if key in cands:
                    continue
                prio = (1.0 if POSITION_CONTEXT.search(context) else 0) + dept.relevance_score / 10
                cands[key] = Candidate(name, purl, dept, page, context, prio)
            # Pagination and sub-listings (e.g. tabs for 教授 / 副教授) on the same host.
            same_host = hostname(page.final_url)
            for ln in pagination_links(page.links):
                if hostname(ln.url) == same_host and canonical_key(ln.url) not in visited:
                    queue.append(ln.url)
            if not people:
                for ln, _ in top_links(page.links, "faculty", limit=3):
                    if hostname(ln.url) == same_host and canonical_key(ln.url) not in visited:
                        queue.append(ln.url)
    # Stable order: higher-priority departments/listings first, then listing order.
    return sorted(cands.values(), key=lambda c: c.priority, reverse=True)


def _generic_emails(ctx: ResearchContext, cand: Candidate) -> set[str]:
    """Emails that appear on listing/department pages are site-wide (office, footer) — never a professor's."""
    out = set(extract_emails(cand.listing.text, cand.listing.mailtos))
    dept_page = ctx.pages.get(cand.department.url or "")
    if dept_page:
        out |= set(extract_emails(dept_page.text, dept_page.mailtos))
    return out


def _choose_email(ctx: ResearchContext, emails: list[str], generic: set[str]) -> str | None:
    usable = []
    for e in emails:
        local = e.split("@")[0]
        if e in generic or GENERIC_LOCALPARTS.match(local):
            continue
        if not ctx.settings.allow_non_institutional_emails and not is_institutional_email(e, ctx.domain):
            continue
        usable.append(e)
    usable.sort(key=lambda e: not is_institutional_email(e, ctx.domain))
    return usable[0] if usable else None


def _has_unreadable_email(text: str) -> bool:
    """An email label ("邮箱:", "E-mail:") NOT followed by a readable address — typically an encoded token
    that the page's JavaScript decodes. Footer lines like "办公室邮箱：office@x.edu.cn" don't count."""
    for m in EMAIL_LABEL.finditer(text):
        rest = text[m.end(): m.end() + 80].split("\n", 2)
        # the value is on the same line ("邮箱: x") or, in two-column layouts, on the next line
        value = rest[0].strip(" :：") or (rest[1] if len(rest) > 1 else "")
        if not extract_emails(value):
            return True
    return False


def _position_near_name(text: str, name: str, fallback: str) -> tuple[str | None, str | None]:
    idx = text.find(name) if name else -1
    if idx >= 0:
        en, orig = detect_position(text[max(0, idx - 200): idx + 600])
        if en:
            return en, orig
    return detect_position(fallback)


async def extract_profile(ctx: ResearchContext, cand: Candidate) -> ProfessorInfo:
    page = await ctx.fetch(cand.url)
    is_cn = has_cjk(cand.name_text)
    prof = ProfessorInfo(
        name=strip_honorific(cand.name_text),
        name_chinese=cand.name_text if is_cn else None,
        department=cand.department, department_name=cand.department.name, school=cand.department.school,
        profile_url=page.final_url if page.ok else cand.url, listing_url=cand.listing.final_url,
    )
    prof.sources.append(SourceRef.from_page(cand.listing, "listed_on_faculty_page", ctx.domain,
                                            SourceType.FACULTY_LIST.value))
    if not page.ok:
        prof.notes.append(f"Profile page could not be loaded ({page.error}); details not verified.")
        prof.position, prof.position_original = detect_position(cand.context)
    else:
        prof.profile_ok = True
        prof.profile_text = page.text
        prof.profile_mailtos = page.mailtos
        prof.sources.append(SourceRef.from_page(page, "profile", ctx.domain, SourceType.PROFILE_PAGE.value
                                                if ctx.official(page.final_url) else SourceType.THIRD_PARTY.value))
        generic = _generic_emails(ctx, cand)
        prof.email = _choose_email(ctx, extract_emails(page.text, page.mailtos), generic)
        if not prof.email and _has_unreadable_email(page.text) and ctx.settings.playwright_enabled:
            # The page has an email field but no readable address: many faculty systems fill it in with
            # JavaScript. Render it like a normal visitor's browser would and read it again.
            rendered = await ctx.fetcher.render(page.final_url)
            if rendered is not None:
                page = rendered
                prof.profile_text, prof.profile_mailtos = page.text, page.mailtos
                prof.email = _choose_email(ctx, extract_emails(page.text, page.mailtos), generic)
        prof.position, prof.position_original = _position_near_name(page.text, cand.name_text, cand.context)

        if ctx.llm.available:
            out = await ctx.llm.extract(
                "professor_profile",
                "Extract this person's name, position and email from their university profile page. "
                "English name only if it is written on the page.",
                truncate_for_llm(f"PAGE TITLE: {page.title}\nURL: {page.final_url}\n\n{page.text}",
                                 ctx.settings.llm_max_input_chars),
                ProfessorExtraction)
            if out:
                _merge_llm(ctx, prof, out, page, generic)

    # ---- names ----------------------------------------------------------------
    if prof.name_chinese and not prof.name_is_romanized and has_cjk(prof.name):
        rom = romanize_chinese_name(prof.name_chinese)
        if rom:
            prof.name, prof.name_is_romanized = rom, True
        else:
            prof.notes.append("Romanisation of the Chinese name is ambiguous; Chinese name preserved.")

    if prof.profile_ok and not prof.email:
        personal = [e for e in extract_emails(prof.profile_text, prof.profile_mailtos)
                    if not is_institutional_email(e, ctx.domain)]
        if personal and not ctx.settings.allow_non_institutional_emails:
            prof.notes.append("The profile lists only a personal (non-university) email, which is hidden because "
                              "ALLOW_NON_INSTITUTIONAL_EMAILS is off. Open the profile to see it.")
        else:
            prof.notes.append("Email not publicly listed on the profile page.")
    return prof


def _merge_llm(ctx: ResearchContext, prof: ProfessorInfo, out: ProfessorExtraction, page: Page,
               generic: set[str]) -> None:
    text = f"{page.title}\n{page.text}"
    if not out.is_individual_profile and not prof.email:
        prof.notes.append("LLM judged this page not to be an individual profile.")
        prof.profile_ok = False
        return
    if out.name_english and is_grounded(out.name_english, text) and looks_like_english_name(out.name_english):
        prof.name, prof.name_is_romanized = strip_honorific(out.name_english), False
    if out.name_chinese and is_grounded(out.name_chinese, text) and looks_like_chinese_name(out.name_chinese):
        prof.name_chinese = clean_person_text(out.name_chinese)
    if not prof.email:
        cands = [e.lower() for e in out.emails if e.lower() in extract_emails(page.text, page.mailtos)]
        prof.email = _choose_email(ctx, cands, generic)
    if out.position_original and is_grounded(out.position_original, text):
        prof.position_original = out.position_original
        prof.position = out.position_english or prof.position


async def discover_professors(ctx: ResearchContext) -> list[ProfessorInfo]:
    candidates = await _collect_candidates(ctx)
    if not candidates:
        ctx.warn("No faculty profiles could be located on the department websites.")
        return []
    limit = ctx.max_professors
    ctx.note(f"Found {len(candidates)} faculty links; extracting up to {limit} profiles")
    sem = asyncio.Semaphore(max(1, ctx.settings.max_concurrent_requests))
    done = 0

    async def run(c: Candidate) -> ProfessorInfo:
        nonlocal done
        async with sem:
            try:
                p = await extract_profile(ctx, c)
            except Exception as exc:  # one profile must never fail the job
                ctx.warn(f"Profile extraction failed for {c.name_text}: {exc}")
                p = ProfessorInfo(name=c.name_text, profile_url=c.url, department=c.department,
                                  department_name=c.department.name,
                                  notes=[f"Extraction failed: {type(exc).__name__}"])
            done += 1
            if done % 5 == 0:
                ctx.note(f"Extracted {done} of {min(len(candidates), limit)} profiles")
            return p

    results = await asyncio.gather(*(run(c) for c in candidates[:limit]))
    profs = [p for p in results if p.profile_ok or p.email or any("could not be loaded" in n for n in p.notes)]
    ctx.note(f"Discovered {len(profs)} professors/researchers")
    return profs
