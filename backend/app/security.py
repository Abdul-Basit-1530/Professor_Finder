"""Access control and abuse protection.

* Optional shared access token (APP_ACCESS_TOKEN). The token is entered by the user in
  the UI and kept in their browser — it is never baked into the frontend bundle.
* Per-IP rate limit on starting research jobs (each job crawls dozens of pages).
"""

from __future__ import annotations

import hmac
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.config import get_settings


def require_access(request: Request) -> None:
    token = get_settings().app_access_token
    if not token:
        return
    supplied = request.headers.get("x-access-token", "")
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid access token is required (X-Access-Token).")


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_s: int = 3600) -> None:
        now = time.monotonic()
        q = self._hits[key]
        while q and now - q[0] > window_s:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many research jobs started from this address. Please try again later.")
        q.append(now)


job_limiter = RateLimiter()


def client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
