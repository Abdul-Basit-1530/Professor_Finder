"""Department Discovery Agent — schools/departments relevant to the user's fields."""

from __future__ import annotations

import re

from app.agents.context import DepartmentInfo, ResearchContext, SourceRef
from app.agents.schemas import DepartmentSelection
from app.enums import Verification
from app.services.fields import (
    COMPUTING_DEPT_HINTS_EN,
    COMPUTING_DEPT_HINTS_ZH,
    match_fields,
)
from app.services.html_utils import Link
from app.services.link_classifier import top_links
from app.services.text_utils import has_cjk
from app.services.url_utils import canonical_key, hostname

UNIT_RE = re.compile(r"学院|学系|系$|研究院|研究所|School|College|Department|Faculty|Institute|Academy", re.I)
URL_HINTS = {"cs", "cse", "scs", "sse", "soft", "software", "ai", "jsj", "cst", "ise", "sist", "seie", "it",
             "cyber", "cybersec", "infosec", "iiis", "sice", "scse", "csse", "ics", "icst", "ss", "sai", "dsai",
             "computer", "computing", "informatics", "nlp", "cv", "iot"}
_EN_TITLE_SEG = re.compile(r"(School|College|Department|Faculty|Institute)\s+of\s+[A-Z][\w &,\-]+")


_MORE_RE = re.compile(r"\s*(?:查看更多|更多|MORE|More|more|>>|»)\s*$")
_NEWSY_PATH = re.compile(r"/(?:info|view|content|article|news|s|detail|show)/|/\d{3,}[/.]|\.jsp\?|[?&]id=", re.I)


def _is_subdomain_root(url: str, domain: str) -> bool:
    """https://cs.x.edu.cn/ — departments usually have their own subdomain homepage."""
    host = hostname(url)
    path = url.split(host, 1)[-1].split("?")[0]
    return host not in (domain, "www." + domain) and path in ("", "/", "/index.htm", "/index.html",
                                                                 "/main.htm", "/index.jsp", "/index.php")


def _url_hint_score(url: str) -> float:
    host = hostname(url)
    labels = set(host.split(".")[:-2])
    path_tokens = set(re.split(r"[/._\-]+", url.split("://", 1)[-1].split("/", 1)[-1].lower()))
    return 2.0 if labels & URL_HINTS else (1.0 if path_tokens & URL_HINTS else 0.0)


_HEADLINE_RE = re.compile(r"举办|举行|召开|会议|论坛|讲座|报告会|开幕|新闻|通知|公告|喜报|荣获|\d{4}|news|event|seminar|"
                          r"workshop|conference|lecture|announce", re.I)


def _candidate_score(ctx: ResearchContext, ln: Link) -> tuple[float, list[dict]]:
    text = _MORE_RE.sub("", ln.text.strip())
    if not text or len(text) > 45 or _HEADLINE_RE.search(text) or text.startswith(("【", "[")):
        return 0.0, []
    matches = match_fields(text, ctx.fields)
    low = text.lower()
    computing = any(h in low for h in COMPUTING_DEPT_HINTS_EN) or any(h in text for h in COMPUTING_DEPT_HINTS_ZH)
    is_unit = bool(UNIT_RE.search(text))
    score = 3.0 * len(matches) + (2.0 if computing else 0.0) + _url_hint_score(ln.url)
    if _is_subdomain_root(ln.url, ctx.domain):
        score += 2.5
    elif _NEWSY_PATH.search(ln.url):
        score -= 3.0
    if is_unit:
        score += 1.5
    elif not matches or score < 4 or len(text) > 16:
        # Non-unit links ("电子地图", "信息公开", museums…) need a real field match, not just a generic hint.
        return 0.0, []
    return score, matches


async def discover_departments(ctx: ResearchContext) -> list[DepartmentInfo]:
    # Open "Schools/Departments" index pages first — they list every unit.
    base_links = ctx.all_links()
    for ln, _ in top_links(base_links, "schools", limit=2):
        await ctx.fetch(ln.url)
    links = ctx.all_links()

    scored: dict[str, tuple[Link, float, list[dict]]] = {}
    for ln in links:
        s, m = _candidate_score(ctx, ln)
        if s >= 3.5:
            key = canonical_key(ln.url)
            if key not in scored or scored[key][1] < s:
                scored[key] = (ln, s, m)
    cands = sorted(scored.values(), key=lambda t: t[1], reverse=True)[:30]

    if not cands and ctx.search.available:
        ctx.note("No department links found in navigation; searching the official domain")
        for q in ("计算机学院", "School of Computer Science", "软件学院", "人工智能学院"):
            for r in await ctx.search.search(q, site=ctx.domain):
                if ctx.official(r.url):
                    ln = Link(url=r.url, text=r.title[:45])
                    s, m = _candidate_score(ctx, ln)
                    if s > 0:
                        cands.append((ln, s, m))
            if cands:
                break

    chosen: list[tuple[Link, float, list[dict], str | None]] = [(ln, s, m, None) for ln, s, m in cands]
    if ctx.llm.available and len(cands) > 1:
        listing = "\n".join(f"[{i}] {ln.text} — {ln.url}" for i, (ln, _, _) in enumerate(cands))
        out = await ctx.llm.extract(
            "department_selection",
            "From these links on a university website, choose the schools/departments whose teaching or research "
            f"relates to: {', '.join(f.label for f in ctx.fields)}. Return their indices and English names.",
            listing, DepartmentSelection)
        if out and out.departments:
            picked = []
            for d in out.departments:
                if 0 <= d.index < len(cands):
                    ln, s, m = cands[d.index]
                    picked.append((ln, s + 2, m, d.name_english))
            if picked:
                chosen = sorted(picked, key=lambda t: t[1], reverse=True)

    # The same unit is often linked from both the Chinese and English sites.
    aliases: dict[str, list[str]] = {}
    for ln in (x for p in ctx.pages.values() for x in p.links):
        if ln.text.strip() and len(ln.text) <= 45:
            aliases.setdefault(canonical_key(ln.url), []).append(ln.text.strip())

    departments: list[DepartmentInfo] = []
    blocked: list[str] = []
    seen_hosts: set[str] = set()
    for ln, score, matches, en_name in chosen:
        if len(departments) >= ctx.settings.max_departments:
            break
        page = await ctx.fetch(ln.url)
        if not page.ok:
            label = _MORE_RE.sub("", ln.text)
            if page.blocked:
                blocked.append(f"{label} ({page.final_url})")
            else:
                ctx.warn(f"Department page unavailable: {label} ({page.error or 'empty page'})")
            continue
        if not ctx.official(page.final_url):
            continue  # e.g. admissions cards that redirect to WeChat articles
        key = canonical_key(page.final_url)
        if key in seen_hosts:
            continue
        seen_hosts.add(key)
        alt = aliases.get(canonical_key(ln.url), []) + aliases.get(key, [])
        ln = type(ln)(url=ln.url, text=_MORE_RE.sub("", ln.text).strip(), context=ln.context)
        name_zh = ln.text if has_cjk(ln.text) else next((t for t in alt if has_cjk(t) and UNIT_RE.search(t)), None)
        name = en_name or (ln.text if not has_cjk(ln.text) else None) or next(
            (t for t in alt if not has_cjk(t) and UNIT_RE.search(t)), None)
        if not name:
            m = _EN_TITLE_SEG.search(page.title + "\n" + page.text[:1500])
            name = m.group(0).strip() if m else ln.text
        page_matches = match_fields(f"{ln.text} {page.title} {page.text[:2500]}", ctx.fields)
        all_matches = {x["label"] for x in matches} | {x["label"] for x in page_matches}
        faculty = [f.url for f, _ in top_links(page.links, "faculty", limit=ctx.settings.max_faculty_list_pages)
                   if ctx.official(f.url)]
        dept = DepartmentInfo(
            name=name, name_chinese=name_zh, url=page.final_url, faculty_list_urls=faculty,
            matched_fields=sorted(all_matches), relevance_score=round(score + 0.5 * len(page_matches), 2),
            school=name if UNIT_RE.search(name or "") and re.search(r"学院|School|College|Faculty", name or "", re.I) else None,
            verification_status=Verification.VERIFIED.value if ctx.official(page.final_url)
            else Verification.PARTIALLY_VERIFIED.value,
            sources=[SourceRef.from_page(page, "department", ctx.domain)],
        )
        departments.append(dept)
        ctx.note(f"Relevant unit: {dept.name}" + (f" ({name_zh})" if name_zh and name_zh != dept.name else "")
                 + f" — {len(faculty)} faculty listing link(s)")

    if blocked:
        ctx.warn(f"{len(blocked)} relevant school website(s) are protected by anti-bot checks and could not be read "
                 f"automatically — please check them manually: " + "; ".join(blocked[:6]))
    if not departments:
        ctx.warn("No relevant school/department could be identified from the website navigation.")
        # Last resort: look for faculty directories linked directly from the fetched pages.
        faculty = [f.url for f, _ in top_links(ctx.all_links(), "faculty", limit=3)]
        if faculty and ctx.homepage:
            departments.append(DepartmentInfo(
                name=ctx.university.name if ctx.university else "University", url=ctx.homepage.final_url,
                faculty_list_urls=faculty, verification_status=Verification.PARTIALLY_VERIFIED.value,
                sources=[SourceRef.from_page(ctx.homepage, "department", ctx.domain)]))

    departments.sort(key=lambda d: d.relevance_score, reverse=True)
    ctx.departments = departments
    return departments
