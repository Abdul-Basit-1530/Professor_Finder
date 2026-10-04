"""End-to-end research pipeline against the mock university (no network)."""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import select

from app import models as m
from app.agents.orchestrator import Orchestrator, initial_steps
from app.db import SessionLocal
from app.services.exporter import export_csv, export_excel, export_pdf
from app.services.text_utils import extract_emails
from tests.mock_site import ROOT, all_site_text, site_transport

FIELDS = ["Artificial Intelligence", "Natural Language Processing", "Machine Learning", "Computer Vision",
          "Software Engineering", "Distributed Systems", "Cloud Computing"]


def run_job(settings, url=ROOT + "/", fields=FIELDS, **opts) -> str:
    with SessionLocal() as db:
        job = m.ResearchJob(id="job" + str(abs(hash((url, tuple(fields)))) % 10**8), university_url=url,
                            fields=fields, options=dict(opts), status="queued",
                            steps=initial_steps(), warnings=[], stats={})
        db.add(job)
        db.commit()
        jid = job.id
    asyncio.run(Orchestrator(jid, settings=settings, transport=site_transport()).run())
    return jid


@pytest.fixture()
def job_id(db_url, test_settings):
    return run_job(test_settings)


def profs_by_cn(db, job_id):
    rows = db.scalars(select(m.Professor).where(m.Professor.job_id == job_id)).all()
    return {p.name_chinese or p.name: p for p in rows}


def test_job_completes_with_all_steps(job_id):
    with SessionLocal() as db:
        job = db.get(m.ResearchJob, job_id)
        assert job.status == "completed", job.error_message
        assert job.progress == 100
        assert [s["key"] for s in job.steps] == ["university", "departments", "professors", "verification", "results"]
        assert all(s["status"] == "done" for s in job.steps), job.steps
        assert any("heuristic-only" in w for w in job.warnings)


def test_only_needed_pages_are_crawled(job_id):
    """Scholarship / program pages are no longer part of the workflow and must not be fetched."""
    with SessionLocal() as db:
        cached = {r.url for r in db.scalars(select(m.PageCache))}
        assert not any("scholarships" in u or "programs" in u or "gs.mocku" in u for u in cached)
        assert any("/szdw/" in u for u in cached)


def test_university_identified(job_id):
    with SessionLocal() as db:
        job = db.get(m.ResearchJob, job_id)
        uni = db.get(m.University, job.university_id)
        assert uni.name == "Mock University"
        assert uni.name_chinese == "模拟大学"
        assert uni.country == "China"
        assert "Beijing" in uni.location
        assert uni.verification_status == "VERIFIED"


def test_relevant_departments_only(job_id):
    with SessionLocal() as db:
        depts = db.scalars(select(m.Department).where(m.Department.job_id == job_id)).all()
        joined = " ".join((d.name_chinese or "") + d.name for d in depts)
        assert "计算机" in joined and "软件" in joined
        assert "外国语" not in joined and "化学" not in joined


def test_professors_extracted_verified_and_deduplicated(job_id):
    with SessionLocal() as db:
        profs = profs_by_cn(db, job_id)
        # 张伟 appears on two Chinese list pages and on the English site -> one record
        zhang = [p for p in profs.values() if p.email == "zhangwei@mocku.edu.cn"]
        assert len(zhang) == 1
        z = zhang[0]
        assert z.name == "Wei Zhang" and z.name_chinese == "张伟"
        assert z.position == "Professor"
        assert z.email_verified and z.email_status == "VERIFIED EMAIL"
        assert z.profile_url.startswith("https://cs.mocku.edu.cn/")
        assert z.verification_status == "VERIFIED"

        li = profs["李娜"]
        assert li.name == "Li Na" and li.email == "lina@mocku.edu.cn"
        assert li.profile_url == "https://cs.mocku.edu.cn/szdw/lina.htm"
        assert li.verification_status == "VERIFIED"

        zeng = profs["曾华"]  # 曾 is ambiguous (Zeng/Ceng): Chinese name preserved, no guessed pinyin
        assert zeng.name == "曾华" and not zeng.name_is_romanized
        assert zeng.email is None and zeng.email_status == "EMAIL NOT FOUND"
        assert zeng.verification_status == "PARTIALLY VERIFIED"

        liu = profs["刘洋"]
        assert liu.email is None  # gmail address is not institutional -> not collected

        wang = profs["王强"]  # broken profile link
        assert wang.verification_status == "NOT VERIFIED"
        assert any("could not be loaded" in n for n in wang.notes)

        smith = [p for p in profs.values() if p.name == "John Smith"][0]
        assert smith.email == "jsmith@sse.mocku.edu.cn"  # "jsmith [at] sse.mocku.edu.cn" on the page
        assert profs["陈静"].email == "chenjing@sse.mocku.edu.cn"


def test_professors_with_email_listed_first(job_id):
    with SessionLocal() as db:
        rows = db.scalars(select(m.Professor).where(m.Professor.job_id == job_id)
                          .order_by(m.Professor.sort_order)).all()
        statuses = [p.verification_status for p in rows]
        assert statuses == sorted(statuses, key=lambda s: {"VERIFIED": 0, "PARTIALLY VERIFIED": 1}.get(s, 2))


def test_every_professor_has_profile_link_and_sources(job_id):
    with SessionLocal() as db:
        for p in db.scalars(select(m.Professor).where(m.Professor.job_id == job_id)):
            assert p.profile_url and p.profile_url.startswith("https://")
            srcs = db.scalars(select(m.Source).where(m.Source.entity_type == "professor",
                                                     m.Source.entity_id == p.id)).all()
            assert srcs


def test_no_fabricated_or_office_emails(job_id):
    site_emails = set(extract_emails(all_site_text()))
    with SessionLocal() as db:
        for p in db.scalars(select(m.Professor).where(m.Professor.job_id == job_id)):
            if p.email:
                assert p.email in site_emails
                assert p.email not in ("cs@mocku.edu.cn", "office@mocku.edu.cn")


def test_robots_txt_respected(job_id):
    with SessionLocal() as db:
        cached = {r.url for r in db.scalars(select(m.PageCache))}
        assert not any("/private/" in u for u in cached)
        assert ROOT + "/" in cached


def test_cache_reused_on_second_run(job_id, test_settings):
    second = run_job(test_settings, fields=["Computer Vision"])
    with SessionLocal() as db:
        assert db.get(m.ResearchJob, second).stats["cache_hits"] > 0


def test_max_professors_limit(db_url, test_settings):
    jid = run_job(test_settings, max_professors=2)
    with SessionLocal() as db:
        assert len(db.scalars(select(m.Professor).where(m.Professor.job_id == jid)).all()) <= 2


def test_exports(job_id):
    with SessionLocal() as db:
        csv_text = export_csv(db, job_id).decode("utf-8-sig")
        assert csv_text.splitlines()[0].startswith("Professor,Chinese Name,Position,Department,Email")
        assert "zhangwei@mocku.edu.cn" in csv_text and "Not publicly listed" in csv_text
        assert "https://cs.mocku.edu.cn/szdw/lina.htm" in csv_text
        assert export_excel(db, job_id)[:2] == b"PK"
        assert export_pdf(db, job_id)[:4] == b"%PDF"


def test_unreachable_site_fails_gracefully(db_url, test_settings):
    jid = run_job(test_settings, url="https://nonexistent.mocku.edu.cn/")
    with SessionLocal() as db:
        job = db.get(m.ResearchJob, jid)
        assert job.status == "failed"
        assert "Could not load" in job.error_message


def test_hidden_personal_email_is_explained(job_id):
    with SessionLocal() as db:
        liu = profs_by_cn(db, job_id)["刘洋"]  # profile lists only liuyang@gmail.com
        assert liu.email is None
        assert any("personal (non-university) email" in n for n in liu.notes)
