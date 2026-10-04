"""Polite, cached web fetcher.

Responsibilities
* SSRF protection (no private/loopback targets, re-checked on every redirect)
* robots.txt compliance (per host, cached)
* per-host rate limiting + global concurrency cap + per-job page budget
* charset detection (GBK/GB2312/GB18030 are common on Chinese sites)
* PDF text extraction
* optional Playwright rendering for JavaScript-heavy pages
* CAPTCHA / block detection (we never try to bypass it — the page is marked blocked)
* persistent page cache (url, content hash, fetched time) with TTL + force refresh

`fetch()` never raises for network problems: it returns a `Page` with `error` set,
so one bad page can't crash a research job.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from sqlalchemy import select

from app.config import Settings
from app.services.html_utils import (
    Link,
    decode_html,
    looks_blocked,
    looks_js_rendered,
    parse_html,
)
from app.services.text_utils import detect_language, normalize_space
from app.services.url_utils import host_is_public, hostname, is_pdf_url, normalize_url

log = logging.getLogger("agent.fetcher")


@dataclass
class Page:
    url: str
    final_url: str
    status: int = 0
    content_type: str = ""
    title: str = ""
    text: str = ""
    html: str = ""
    links: list[Link] = field(default_factory=list)
    mailtos: list[str] = field(default_factory=list)
    table_rows: list[list[str]] = field(default_factory=list)
    lang: str = "en"
    is_pdf: bool = False
    from_cache: bool = False
    blocked: bool = False
    render_mode: str = "http"
    error: str | None = None
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 300 and bool(self.text)


class BudgetExceeded(Exception):
    pass


class Fetcher:
    def __init__(
        self,
        settings: Settings,
        *,
        session_factory=None,
        transport: httpx.AsyncBaseTransport | None = None,
        force_refresh: bool = False,
        max_pages: int | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.force_refresh = force_refresh
        self.max_pages = max_pages or settings.max_pages_per_job
        self._transport = transport
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
                "Accept-Language": "en,zh-CN;q=0.9,zh;q=0.8",
            },
            follow_redirects=False,
        )
        self._sem = asyncio.Semaphore(settings.max_concurrent_requests)
        self._host_locks: dict[str, asyncio.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._memo: dict[str, Page] = {}
        self._inflight: dict[str, asyncio.Future] = {}
        self._browser = None
        self._pw = None
        self._browser_lock = asyncio.Lock()
        self.network_fetches = 0
        self.cache_hits = 0
        self.errors = 0

    # ------------------------------------------------------------------ public
    async def fetch(self, url: str, *, allow_render: bool = True) -> Page:
        url = normalize_url(url)
        if url in self._memo:
            return self._memo[url]
        if url in self._inflight:
            return await self._inflight[url]
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._inflight[url] = fut
        try:
            page = await self._fetch_uncached_memo(url, allow_render)
        except Exception as exc:  # defensive: never propagate
            log.exception("Unexpected fetch failure for %s", url)
            page = Page(url=url, final_url=url, error=f"unexpected error: {exc}")
        self._memo[url] = page
        fut.set_result(page)
        self._inflight.pop(url, None)
        if page.error:
            self.errors += 1
        return page

    async def render(self, url: str) -> Page | None:
        """Force a Playwright render (e.g. a faculty list whose names are loaded by JavaScript)."""
        if not self.settings.playwright_enabled or self.network_fetches >= self.max_pages:
            return None
        page = await self._render(normalize_url(url))
        if page is not None and page.text.strip():
            self._memo[normalize_url(url)] = page
            self._cache_put(page)
            return page
        return None

    @property
    def budget_left(self) -> int:
        return self.max_pages - self.network_fetches

    async def aclose(self) -> None:
        await self._client.aclose()
        if self._browser is not None:
            try:
                await self._browser.close()
                await self._pw.stop()
            except Exception:  # pragma: no cover
                pass

    # ------------------------------------------------------------------ internals
    async def _fetch_uncached_memo(self, url: str, allow_render: bool) -> Page:
        cached = None if self.force_refresh else self._cache_get(url)
        if cached is not None:
            self.cache_hits += 1
            return cached

        if self.network_fetches >= self.max_pages:
            return Page(url=url, final_url=url, error="page budget exhausted")

        host = hostname(url)
        if self.settings.ssrf_protection and self._transport is None:
            if not await asyncio.to_thread(host_is_public, host):
                return Page(url=url, final_url=url, error="host is not publicly routable or does not resolve")

        if self.settings.respect_robots_txt and not await self._robots_allowed(url):
            log.info("robots.txt disallows %s", url)
            return Page(url=url, final_url=url, error="disallowed by robots.txt")

        page = await self._http_get(url)
        needs_js = (
            not page.is_pdf
            and (
                (page.status in (200, 203) and looks_js_rendered(page.html, page.text))
                or (200 <= page.status < 300 and not page.text.strip())
                or page.status == 412  # common JS-cookie challenge on Chinese WAFs
            )
        )
        if needs_js and allow_render and self.settings.playwright_enabled:
            rendered = await self._render(url)
            if rendered is not None and rendered.text.strip():
                page = rendered
                if looks_blocked(page.status, page.text):
                    page.blocked, page.error = True, "blocked / CAPTCHA page detected"
            elif not page.text.strip():
                # We never try to evade bot protection (no fingerprint spoofing / stealth).
                page.blocked, page.error = True, "protected by an anti-bot check that rejects automated browsers; open this page manually to verify its information"
        elif needs_js and not page.error and not page.text.strip():
            page.error = ("page requires JavaScript (dynamic page or anti-bot check); "
                          "enable PLAYWRIGHT_ENABLED to render it")
        if page.status == 200 and not page.error:
            self._cache_put(page)
        return page

    async def _throttle(self, host: str) -> None:
        lock = self._host_locks.setdefault(host, asyncio.Lock())
        async with lock:
            wait = self._host_last.get(host, 0) + self.settings.request_delay_seconds - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._host_last[host] = time.monotonic()

    async def _http_get(self, url: str, _attempt: int = 0) -> Page:
        current = url
        async with self._sem:
            for _ in range(6):  # manual redirects so each hop is SSRF-checked
                host = hostname(current)
                await self._throttle(host)
                self.network_fetches += 1
                try:
                    resp = await self._client.get(current)
                except httpx.TimeoutException:
                    return Page(url=url, final_url=current, error="timeout")
                except httpx.HTTPError as exc:
                    return Page(url=url, final_url=current, error=f"network error: {type(exc).__name__}")
                if resp.is_redirect and resp.headers.get("location"):
                    nxt = normalize_url(str(resp.url.join(resp.headers["location"])))
                    if (
                        self.settings.ssrf_protection
                        and self._transport is None
                        and not await asyncio.to_thread(host_is_public, hostname(nxt))
                    ):
                        return Page(url=url, final_url=nxt, error="redirect to non-public host blocked")
                    current = nxt
                    continue
                break
            else:
                return Page(url=url, final_url=current, error="too many redirects")

        log.info("Fetched %s -> %s (%s)", url, resp.status_code, resp.headers.get("content-type", ""))
        if resp.status_code == 429 and _attempt == 0:
            retry_after = min(float(resp.headers.get("retry-after", "5") or 5), 30.0)
            log.warning("Rate limited by %s; backing off %.0fs", hostname(url), retry_after)
            await asyncio.sleep(retry_after)
            return await self._http_get(url, _attempt=1)

        ctype = resp.headers.get("content-type", "").lower()
        page = Page(url=url, final_url=str(resp.url), status=resp.status_code, content_type=ctype)
        if resp.status_code >= 400:
            page.error = "HTTP 412 (JavaScript challenge)" if resp.status_code == 412 else f"HTTP {resp.status_code}"
            page.blocked = resp.status_code in (403, 429, 503)
            return page

        body = resp.content
        if "pdf" in ctype or is_pdf_url(str(resp.url)) or body[:5] == b"%PDF-":
            page.is_pdf = True
            page.text = await asyncio.to_thread(self._pdf_text, body)
            page.title = urlsplit(str(resp.url)).path.rsplit("/", 1)[-1]
            page.lang = detect_language(page.text)
            if not page.text:
                page.error = "PDF contains no extractable text (possibly scanned)"
            return page
        if "html" not in ctype and "xml" not in ctype and ctype:
            page.error = f"unsupported content type {ctype}"
            return page

        page.html = decode_html(body, resp.charset_encoding)
        self._fill_from_html(page)
        if looks_blocked(page.status, page.text):
            page.blocked = True
            page.error = "blocked / CAPTCHA page detected"
            log.warning("Block/CAPTCHA detected at %s — not bypassing", url)
        return page

    def _fill_from_html(self, page: Page) -> None:
        title, text, links, mailtos, rows = parse_html(page.html, page.final_url)
        page.title, page.text, page.links, page.mailtos, page.table_rows = title, text, links, mailtos, rows
        page.lang = detect_language(text)

    def _pdf_text(self, data: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            parts = []
            for pg in reader.pages[: self.settings.max_pdf_pages]:
                parts.append(pg.extract_text() or "")
            return normalize_space("\n".join(parts))
        except Exception as exc:
            log.warning("PDF extraction failed: %s", exc)
            return ""

    async def _render(self, url: str) -> Page | None:
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            log.info("Playwright not installed; skipping JS rendering for %s", url)
            return None
        try:
            async with self._browser_lock:
                if self._browser is None:
                    self._pw = await async_playwright().start()
                    self._browser = await self._pw.chromium.launch(headless=True)
        except Exception as exc:
            log.warning("Could not start Playwright: %s", exc)
            return None
        for attempt in range(2):
            ctx = None
            try:
                ctx = await self._browser.new_context(user_agent=self.settings.user_agent)
                pg = await ctx.new_page()
                await self._throttle(hostname(url))
                self.network_fetches += 1
                # Don't wait for "network idle": pages with visit counters / analytics never go idle.
                resp = await pg.goto(url, wait_until="domcontentloaded",
                                     timeout=self.settings.request_timeout_seconds * 1000)
                try:
                    await pg.wait_for_load_state("load", timeout=8000)
                except Exception:
                    pass  # scripts still loading — the content poll below decides
                # Give client-side rendering a few seconds to populate the page.
                await pg.wait_for_timeout(1000)
                for _ in range(5):
                    if len((await pg.inner_text("body")).strip()) > 300:
                        break
                    await pg.wait_for_timeout(1000)
                html = await pg.content()
                page = Page(url=url, final_url=pg.url, status=resp.status if resp else 200,
                            content_type="text/html", html=html, render_mode="playwright")
                self._fill_from_html(page)
                log.info("Rendered %s with Playwright", url)
                return page
            except Exception as exc:
                log.warning("Playwright render failed for %s (attempt %d): %s", url, attempt + 1, str(exc)[:150])
            finally:
                if ctx is not None:
                    try:
                        await ctx.close()
                    except Exception:
                        pass
        return None

    async def _robots_allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp: RobotFileParser | None = None
            try:
                await self._throttle(parts.hostname or "")
                resp = await self._client.get(origin + "/robots.txt")
                if resp.status_code == 200 and "text" in resp.headers.get("content-type", "text"):
                    rp = RobotFileParser()
                    rp.parse(decode_html(resp.content, resp.charset_encoding).splitlines())
            except httpx.HTTPError:
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return True if rp is None else rp.can_fetch(self.settings.user_agent, url)

    # ------------------------------------------------------------------ cache
    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    def _cache_get(self, url: str) -> Page | None:
        if self.session_factory is None:
            return None
        from app.models import PageCache

        try:
            with self.session_factory() as db:
                row = db.scalar(select(PageCache).where(PageCache.url_hash == self._url_hash(url)))
                if row is None:
                    return None
                fetched = row.fetched_at if row.fetched_at.tzinfo else row.fetched_at.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) - fetched > timedelta(hours=self.settings.cache_ttl_hours):
                    return None
                page = Page(url=url, final_url=row.final_url, status=row.status_code,
                            content_type=row.content_type or "", from_cache=True,
                            render_mode=row.render_mode, fetched_at=fetched)
                if row.html:
                    page.html = row.html
                    self._fill_from_html(page)
                else:
                    page.is_pdf = True
                    page.text = row.text or ""
                    page.lang = detect_language(page.text)
                    page.title = urlsplit(row.final_url).path.rsplit("/", 1)[-1]
                return page
        except Exception as exc:  # cache problems must never break research
            log.warning("Cache read failed: %s", exc)
            return None

    def _cache_put(self, page: Page) -> None:
        if self.session_factory is None:
            return
        from app.models import PageCache

        content = page.html or page.text
        chash = hashlib.sha256(content.encode("utf-8", "ignore")).hexdigest()
        try:
            with self.session_factory() as db:
                h = self._url_hash(page.url)
                row = db.scalar(select(PageCache).where(PageCache.url_hash == h))
                if row is None:
                    row = PageCache(url_hash=h, url=page.url)
                    db.add(row)
                row.final_url = page.final_url
                row.status_code = page.status
                row.content_type = page.content_type
                row.content_hash = chash
                row.html = page.html or None
                row.text = None if page.html else page.text
                row.render_mode = page.render_mode
                row.fetched_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as exc:
            log.warning("Cache write failed: %s", exc)
