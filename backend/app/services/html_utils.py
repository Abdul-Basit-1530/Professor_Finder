"""HTML parsing: visible text, links, title, tables, charset handling."""

from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.services.text_utils import normalize_space
from app.services.url_utils import resolve_link

try:  # lxml is much faster; html.parser is the stdlib fallback
    import lxml  # noqa: F401

    _PARSER = "lxml"
except ImportError:  # pragma: no cover
    _PARSER = "html.parser"


@dataclass
class Link:
    url: str
    text: str
    context: str = ""  # text of the surrounding element (helps classify person links)


_META_CHARSET_RE = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-]+)""", re.IGNORECASE)


def decode_html(raw: bytes, header_charset: str | None) -> str:
    """Decode HTML bytes. Chinese sites frequently use GBK/GB2312 without a header."""
    # Bytes that are valid UTF-8 are almost never GBK text, while GB18030 will "successfully"
    # decode UTF-8 into mojibake — so strict UTF-8 wins whenever it works.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    candidates: list[str] = []
    if header_charset:
        candidates.append(header_charset)
    m = _META_CHARSET_RE.search(raw[:4096])
    if m:
        candidates.append(m.group(1).decode("ascii", "ignore"))
    candidates += ["utf-8", "gb18030"]
    for enc in candidates:
        enc = enc.lower().strip()
        if enc in ("gb2312", "gbk", "gb_2312-80", "x-gbk"):
            enc = "gb18030"  # superset, decodes both
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def parse_html(html: str, base_url: str) -> tuple[str, str, list[Link], list[str], list[list[str]]]:
    """Return (title, visible_text, links, mailto_addresses, table_rows)."""
    soup = BeautifulSoup(html, _PARSER)
    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
    og = soup.find("meta", attrs={"property": "og:site_name"})
    if og and og.get("content"):
        title = title or og["content"].strip()

    mailtos: list[str] = []
    links: list[Link] = []
    seen: set[str] = set()
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if href.lower().startswith("mailto:"):
            mailtos.append(href[7:])
            continue
        url = resolve_link(base_url, href)
        if not url:
            continue
        text = a.get_text(" ", strip=True) or a.get("title") or ""
        if not text:
            img = a.find("img")
            if img is not None:
                text = img.get("alt") or ""
        text = re.sub(r"\s+", " ", text).strip()[:200]
        parent = a.find_parent(["li", "tr", "div", "td", "p", "dd"])
        context = re.sub(r"\s+", " ", parent.get_text(" ", strip=True))[:300] if parent else ""
        key = url + "|" + text
        if key in seen:
            continue
        seen.add(key)
        links.append(Link(url=url, text=text, context=context))

    rows: list[list[str]] = []
    for tr in soup.find_all("tr"):
        cells = [re.sub(r"\s+", " ", c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells)

    for tag in soup(["script", "style", "noscript", "svg", "iframe", "template"]):
        tag.decompose()
    text = normalize_space(soup.get_text("\n"))
    return title, text, links, mailtos, rows


def looks_js_rendered(html: str, text: str) -> bool:
    """Heuristic: very little visible text but lots of script — probably an SPA."""
    if len(text) >= 400:
        return False
    scripts = html.lower().count("<script")
    return scripts >= 3 or "enable javascript" in html.lower() or 'id="app"' in html or 'id="root"' in html


_BLOCK_MARKERS = (
    "captcha", "验证码", "人机验证", "安全验证", "access denied", "are you a robot", "滑动验证",
    "请开启javascript", "cf-challenge", "challenge-platform",
)


def looks_blocked(status: int, text: str) -> bool:
    if status in (401, 403, 429, 503):
        return True
    low = text[:3000].lower()
    return len(text) < 1500 and any(m in low for m in _BLOCK_MARKERS)
