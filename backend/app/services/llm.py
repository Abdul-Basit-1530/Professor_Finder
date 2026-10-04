"""Provider-agnostic LLM layer with schema-validated JSON output.

Agents call `llm.extract(task, system, content, Schema)` and receive either a
validated Pydantic object or `None`. `None` means "LLM unavailable or failed" and
every agent has a deterministic fallback, so an LLM outage degrades quality but
never fabricates or crashes.

To swap providers implement `LLMProvider.complete_json`. The OpenAI provider also
works with any OpenAI-compatible endpoint via OPENAI_BASE_URL.
"""

from __future__ import annotations

import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger("agent.llm")

T = TypeVar("T", bound=BaseModel)

GROUNDING_RULES = """You are a careful research-extraction engine for a tool that helps students find
supervisors at Chinese universities.
STRICT RULES:
- Use ONLY the source text provided. Never use outside knowledge to add facts.
- Never invent names, emails, positions, departments or URLs.
- When asked for an `evidence`/`quote`/`original` field, copy it VERBATIM from the source text
  (in its original language, e.g. Chinese). Quotes are machine-checked; non-verbatim quotes are discarded.
- If information is absent, use null or an empty list. Absence is not a negative finding.
- Translate Chinese into clear English for English fields, but keep originals where requested.
- Respond with a single JSON object matching the provided JSON schema. No prose."""


class LLMProvider:
    name = "none"

    @property
    def available(self) -> bool:
        return False

    async def complete_json(self, system: str, user: str) -> str | None:  # pragma: no cover
        return None

    async def extract(self, task: str, instructions: str, content: str, schema: type[T]) -> T | None:
        """Ask for JSON matching `schema`; validate; one repair retry on validation error."""
        if not self.available:
            return None
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system = f"{GROUNDING_RULES}\n\nTASK: {task}\n\nJSON schema:\n{schema_json}"
        user = f"{instructions}\n\n=== SOURCE TEXT START ===\n{content}\n=== SOURCE TEXT END ==="
        raw = await self.complete_json(system, user)
        for attempt in range(2):
            if raw is None:
                return None
            try:
                return schema.model_validate_json(_strip_fences(raw))
            except ValidationError as exc:
                log.warning("LLM output failed validation for %s (attempt %d): %s", task, attempt + 1,
                            str(exc)[:300])
                if attempt == 0:
                    raw = await self.complete_json(
                        system,
                        user + f"\n\nYour previous output was invalid: {str(exc)[:800]}\nReturn corrected JSON only.",
                    )
        return None


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


class NullLLM(LLMProvider):
    """Used when no API key is configured — agents fall back to heuristics."""


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, settings: Settings) -> None:
        from openai import AsyncOpenAI

        self.settings = settings
        self.model = settings.llm_model
        self._client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )
        self.calls = 0
        self.failures = 0

    @property
    def available(self) -> bool:
        return True

    async def complete_json(self, system: str, user: str) -> str | None:
        self.calls += 1
        try:
            resp = await self._client.chat.completions.create(
                model=self.model,
                temperature=self.settings.llm_temperature,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return resp.choices[0].message.content
        except Exception as exc:  # network, auth, rate limit, model errors
            self.failures += 1
            log.warning("LLM call failed (%s): %s", type(exc).__name__, str(exc)[:200])
            return None


def build_llm(settings: Settings) -> LLMProvider:
    if settings.llm_enabled:
        try:
            return OpenAIProvider(settings)
        except Exception as exc:  # pragma: no cover
            log.error("Could not initialise OpenAI provider: %s", exc)
    return NullLLM()


def truncate_for_llm(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.8)
    return text[:head] + "\n…[truncated]…\n" + text[-(limit - head):]
