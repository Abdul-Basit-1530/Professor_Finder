"""Agent-level tests: LLM grounding, schema validation, dedup, verification, fetcher robustness."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from app.agents.context import DepartmentInfo, ProfessorInfo, ResearchContext
from app.agents.professors import Candidate, extract_profile
from app.agents.schemas import DepartmentSelection, ProfessorExtraction
from app.agents.verification import verify_professor
from app.services.dedup import deduplicate
from app.services.fetcher import Fetcher
from app.services.fields import resolve_fields
from app.services.llm import LLMProvider, NullLLM
from app.services.search import SearchProvider
from tests.mock_site import CS, site_transport


class FakeLLM(LLMProvider):
    """Returns canned JSON per task — including deliberately fabricated values."""

    name = "fake"

    def __init__(self, responses: dict[str, dict]):
        self.responses = responses
        self.calls: list[str] = []

    @property
    def available(self) -> bool:
        return True

    async def complete_json(self, system: str, user: str) -> str | None:
        task = system.split("TASK: ", 1)[1].split("\n", 1)[0]
        self.calls.append(task)
        r = self.responses.get(task)
        return json.dumps(r) if r is not None else None


def make_ctx(settings, llm=None) -> ResearchContext:
    return ResearchContext(
        job_id="t", start_url="https://www.mocku.edu.cn/", domain="mocku.edu.cn",
        fields=resolve_fields(["NLP", "Machine Learning", "Computer Vision"]), settings=settings,
        fetcher=Fetcher(settings, transport=site_transport()), llm=llm or NullLLM(), search=SearchProvider())


async def _profile(ctx: ResearchContext, name: str, path: str):
    listing = await ctx.fetch(CS + "/szdw/index.htm")
    cand = Candidate(name, CS + path, DepartmentInfo(name="School of CS", url=CS + "/"), listing, "", 1.0)
    return await extract_profile(ctx, cand)


def test_llm_values_are_grounded_and_fabrications_dropped(test_settings):
    fake = FakeLLM({"professor_profile": {
        "is_individual_profile": True,
        "name_english": "David Zhang",  # NOT on the page -> must be ignored
        "name_chinese": "张伟",
        "position_english": "Professor", "position_original": "教授",
        "emails": ["wei.zhang@mocku.edu.cn"],  # fabricated
    }})
    ctx = make_ctx(test_settings, fake)
    prof = asyncio.run(_profile(ctx, "张伟", "/szdw/zhangwei.htm"))
    assert "professor_profile" in fake.calls
    assert prof.email == "zhangwei@mocku.edu.cn"  # the real (obfuscated) one, not the invented one
    assert prof.name == "Zhang Wei" and prof.name_is_romanized  # LLM English name rejected (not on page)
    assert prof.position == "Professor"


def test_llm_never_adds_an_email_that_is_not_on_the_page(test_settings):
    fake = FakeLLM({"professor_profile": {
        "is_individual_profile": True, "name_chinese": "曾华", "emails": ["zenghua@mocku.edu.cn"]}})
    prof = asyncio.run(_profile(make_ctx(test_settings, fake), "曾华", "/szdw/zenghua.htm"))
    assert prof.email is None
    assert any("not publicly listed" in n for n in prof.notes)


def test_llm_failure_falls_back_to_heuristics(test_settings):
    prof = asyncio.run(_profile(make_ctx(test_settings, FakeLLM({})), "李娜", "/szdw/lina.htm"))
    assert prof.email == "lina@mocku.edu.cn"
    assert prof.position == "Associate Professor"


def test_llm_schema_validation_rejects_bad_output():
    with pytest.raises(ValidationError):
        ProfessorExtraction.model_validate({"name_chinese": "张伟"})  # missing is_individual_profile
    with pytest.raises(ValidationError):
        DepartmentSelection.model_validate({"departments": [{"index": "first"}]})


def test_invalid_llm_json_returns_none():
    class Broken(FakeLLM):
        async def complete_json(self, system, user):
            return "not json at all"

    assert asyncio.run(Broken({}).extract("t", "i", "c", ProfessorExtraction)) is None


def test_dedup_merges_by_email_url_and_chinese_name():
    a = ProfessorInfo(name="Zhang Wei", name_chinese="张伟", name_is_romanized=True,
                      profile_url="https://cs.x.edu.cn/zw.htm", profile_ok=True)
    b = ProfessorInfo(name="Wei Zhang", email="zw@x.edu.cn", profile_url="https://cs.x.edu.cn/en/zw.html",
                      profile_ok=True)
    c = ProfessorInfo(name="Zhang Wei", name_chinese="张伟", email="zw@x.edu.cn")
    d = ProfessorInfo(name="Li Na", name_chinese="李娜")
    e = ProfessorInfo(name="Li Na", name_chinese="李娜", profile_url="http://cs.x.edu.cn/ln.htm/")
    out = deduplicate([a, b, c, d, e])
    assert len(out) == 2
    zhang = next(p for p in out if p.name_chinese == "张伟")
    assert zhang.name == "Wei Zhang" and not zhang.name_is_romanized  # page-stated English name wins
    assert zhang.email == "zw@x.edu.cn"


def test_verification_statuses(test_settings):
    ctx = make_ctx(test_settings)
    text = "张伟 教授 邮箱 zw@mocku.edu.cn"
    full = ProfessorInfo(name="Zhang Wei", name_chinese="张伟", name_is_romanized=True, email="zw@mocku.edu.cn",
                         profile_url="https://cs.mocku.edu.cn/zw.htm", profile_text=text, profile_ok=True)
    verify_professor(ctx, full)
    assert full.verification_status == "VERIFIED" and full.email_verified

    no_email = ProfessorInfo(name="Zhang Wei", name_chinese="张伟", name_is_romanized=True,
                             profile_url="https://cs.mocku.edu.cn/zw.htm", profile_text="张伟 教授", profile_ok=True)
    verify_professor(ctx, no_email)
    assert no_email.verification_status == "PARTIALLY VERIFIED" and not no_email.email_verified

    external = ProfessorInfo(name="Zhang Wei", name_chinese="张伟", email="zw@mocku.edu.cn",
                             profile_url="https://someblog.com/zw", profile_text=text, profile_ok=True)
    verify_professor(ctx, external)
    assert external.verification_status == "NOT VERIFIED"  # no official-domain association

    ghost = ProfessorInfo(name="Zhang Wei", name_chinese="张伟", email="ghost@mocku.edu.cn",
                          profile_url="https://cs.mocku.edu.cn/zw.htm", profile_text="张伟 教授", profile_ok=True)
    verify_professor(ctx, ghost)
    assert ghost.email is None  # email not on page -> removed, never presented as fact

    broken = ProfessorInfo(name="Wang Qiang", name_chinese="王强", profile_url="https://cs.mocku.edu.cn/x.htm")
    verify_professor(ctx, broken)
    assert broken.verification_status == "NOT VERIFIED"


def test_fetcher_handles_errors_without_raising(test_settings):
    async def go():
        f = Fetcher(test_settings, transport=site_transport())
        missing = await f.fetch("https://www.mocku.edu.cn/nope.htm")
        blocked = await f.fetch("https://www.mocku.edu.cn/private/secret.htm")
        await f.aclose()
        return missing, blocked

    missing, blocked = asyncio.run(go())
    assert missing.error == "HTTP 404" and not missing.ok
    assert blocked.error == "disallowed by robots.txt"


def test_fetcher_page_budget(test_settings):
    async def go():
        f = Fetcher(test_settings, transport=site_transport(), max_pages=1)
        first = await f.fetch("https://www.mocku.edu.cn/")
        second = await f.fetch("https://www.mocku.edu.cn/en/")
        await f.aclose()
        return first, second

    first, second = asyncio.run(go())
    assert first.ok and second.error == "page budget exhausted"


def test_js_challenge_page_is_reported_not_treated_as_empty_success(test_settings):
    transport = httpx.MockTransport(lambda req: httpx.Response(202, content=b"", headers={"content-type": "text/html"}))

    async def go():
        f = Fetcher(test_settings.model_copy(update={"respect_robots_txt": False}), transport=transport)
        page = await f.fetch("https://www.waf.edu.cn/")
        await f.aclose()
        return page

    page = asyncio.run(go())
    assert not page.ok
    assert "requires JavaScript" in page.error


def test_js_filled_email_is_read_after_rendering(test_settings):
    """Faculty systems that fill the email in with JavaScript: render like a browser, then extract."""
    from app.services.fetcher import Page

    html = ('<html><head><meta charset="utf-8"><title>张伟</title></head><body><h1>张伟</h1><p>教授</p>'
            '<p>邮箱:</p><p>73a51c2682ff5a415ab2247b</p></body></html>')
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=html.encode(),
                                                               headers={"content-type": "text/html"}))
    settings = test_settings.model_copy(update={"playwright_enabled": True, "respect_robots_txt": False})

    class FakeRenderFetcher(Fetcher):
        async def render(self, url):
            return Page(url=url, final_url=url, status=200, text="张伟\n教授\n邮箱:zw_js@mocku.edu.cn",
                        render_mode="playwright")

    ctx = make_ctx(settings)
    ctx.fetcher = FakeRenderFetcher(settings, transport=transport)

    async def go():
        listing = Page(url="https://cs.mocku.edu.cn/list", final_url="https://cs.mocku.edu.cn/list", status=200,
                       text="师资队伍")
        cand = Candidate("张伟", "https://cs.mocku.edu.cn/zw.htm", DepartmentInfo(name="CS", url=None),
                         listing, "", 1.0)
        return await extract_profile(ctx, cand)

    prof = asyncio.run(go())
    assert prof.email == "zw_js@mocku.edu.cn"
    verify_professor(ctx, prof)
    assert prof.email_verified and prof.verification_status == "VERIFIED"


def test_email_filled_by_javascript_is_read_after_rendering(test_settings):
    """Faculty systems often publish the email as an encoded token decoded by JavaScript."""
    from app.services.fetcher import Page

    settings = test_settings.model_copy(update={"playwright_enabled": True})
    ctx = make_ctx(settings)
    rendered_calls = []

    async def fake_render(url):
        rendered_calls.append(url)
        return Page(url=url, final_url=url, status=200, text="曾华 讲师\n邮箱:zenghua@mocku.edu.cn",
                    render_mode="playwright")

    ctx.fetcher.render = fake_render
    prof = asyncio.run(_profile(ctx, "曾华", "/szdw/zenghua.htm"))
    # zenghua.htm has no email label -> no render, stays "not publicly listed"
    assert prof.email is None and rendered_calls == []

    async def go():
        listing = await ctx.fetch(CS + "/szdw/index.htm")
        page = await ctx.fetch(CS + "/szdw/lina.htm")
        page.text = page.text.replace("lina@mocku.edu.cn", "73a51c2682ff5a415ab2")  # encoded on the raw page
        page.mailtos = []
        cand = Candidate("李娜", CS + "/szdw/lina.htm", DepartmentInfo(name="CS", url=CS + "/"), listing, "", 1)
        return await extract_profile(ctx, cand)

    async def render_lina(url):
        rendered_calls.append(url)
        return Page(url=url, final_url=url, status=200, text="李娜 副教授\n邮箱:lina@mocku.edu.cn")

    ctx.fetcher.render = render_lina
    prof = asyncio.run(go())
    assert rendered_calls == [CS + "/szdw/lina.htm"]
    assert prof.email == "lina@mocku.edu.cn"
    verify_professor(ctx, prof)
    assert prof.verification_status == "VERIFIED"  # email re-found in the rendered page text
