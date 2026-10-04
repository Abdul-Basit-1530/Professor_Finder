"""Logging setup with a filter that scrubs anything that looks like a secret."""

from __future__ import annotations

import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)(api[_-]?key|token|authorization|password)\s*[=:]\s*\S+"),
    re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s@]+@"),
]


class SecretScrubber(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        scrubbed = msg
        for pat in _SECRET_PATTERNS:
            scrubbed = pat.sub("[REDACTED]", scrubbed)
        if scrubbed != msg:
            record.msg = scrubbed
            record.args = None
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    )
    handler.addFilter(SecretScrubber())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Third-party noise
    for noisy in ("httpx", "httpcore", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
