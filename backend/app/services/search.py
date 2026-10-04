"""Pluggable web-search providers (used only as a fallback to official-site crawling)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import Settings

log = logging.getLogger("agent.search")


@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str


class SearchProvider:
    name = "none"

    @property
    def available(self) -> bool:
        return False

    async def search(self, query: str, *, site: str | None = None) -> list[SearchResult]:
        return []


class _HTTPSearch(SearchProvider):
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self.max_results = settings.search_max_results
        self._client = httpx.AsyncClient(timeout=20, transport=transport)

    @property
    def available(self) -> bool:
        return True

    async def search(self, query: str, *, site: str | None = None) -> list[SearchResult]:
        q = f"site:{site} {query}" if site else query
        try:
            results = await self._search(q)
            log.info("Search [%s] %r -> %d results", self.name, q, len(results))
            return results[: self.max_results]
        except Exception as exc:
            log.warning("Search failed [%s] %r: %s", self.name, q, exc)
            return []

    async def _search(self, q: str) -> list[SearchResult]:  # pragma: no cover
        raise NotImplementedError


class SerperSearch(_HTTPSearch):
    name = "serper"

    async def _search(self, q: str) -> list[SearchResult]:
        r = await self._client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": self.settings.search_api_key or ""},
            json={"q": q, "num": self.max_results},
        )
        r.raise_for_status()
        return [SearchResult(i.get("link", ""), i.get("title", ""), i.get("snippet", ""))
                for i in r.json().get("organic", [])]


class BraveSearch(_HTTPSearch):
    name = "brave"

    async def _search(self, q: str) -> list[SearchResult]:
        r = await self._client.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers={"X-Subscription-Token": self.settings.search_api_key or "", "Accept": "application/json"},
            params={"q": q, "count": self.max_results},
        )
        r.raise_for_status()
        return [SearchResult(i.get("url", ""), i.get("title", ""), i.get("description", ""))
                for i in r.json().get("web", {}).get("results", [])]


class TavilySearch(_HTTPSearch):
    name = "tavily"

    async def _search(self, q: str) -> list[SearchResult]:
        r = await self._client.post(
            "https://api.tavily.com/search",
            json={"api_key": self.settings.search_api_key, "query": q, "max_results": self.max_results},
        )
        r.raise_for_status()
        return [SearchResult(i.get("url", ""), i.get("title", ""), i.get("content", "")[:300])
                for i in r.json().get("results", [])]


class SearxngSearch(_HTTPSearch):
    name = "searxng"

    async def _search(self, q: str) -> list[SearchResult]:
        r = await self._client.get(
            f"{(self.settings.searxng_url or '').rstrip('/')}/search", params={"q": q, "format": "json"}
        )
        r.raise_for_status()
        return [SearchResult(i.get("url", ""), i.get("title", ""), i.get("content", ""))
                for i in r.json().get("results", [])]


def build_search(settings: Settings) -> SearchProvider:
    p = settings.search_provider
    if p == "serper" and settings.search_api_key:
        return SerperSearch(settings)
    if p == "brave" and settings.search_api_key:
        return BraveSearch(settings)
    if p == "tavily" and settings.search_api_key:
        return TavilySearch(settings)
    if p == "searxng" and settings.searxng_url:
        return SearxngSearch(settings)
    return SearchProvider()
