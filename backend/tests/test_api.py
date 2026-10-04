"""REST API tests (FastAPI TestClient + mock university; jobs run synchronously)."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.agents.orchestrator import Orchestrator
from tests.mock_site import site_transport


class InlineRunner:
    def __init__(self, settings):
        self.settings = settings

    def submit(self, job_id: str) -> None:
        asyncio.run(Orchestrator(job_id, settings=self.settings, transport=site_transport()).run())

    def recover(self):
        pass

    def shutdown(self):
        pass


@pytest.fixture()
def client(db_url, test_settings, monkeypatch):
    from app import jobs
    from app.api import research
    from app.security import job_limiter

    runner = InlineRunner(test_settings)
    monkeypatch.setattr(jobs, "runner", runner)
    monkeypatch.setattr(research, "get_runner", lambda: runner)
    job_limiter._hits.clear()
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def job_id(client):
    r = client.post("/api/research/start", json={
        "university_url": "www.mocku.edu.cn", "fields": ["NLP", "Computer Vision"],
        "custom_fields": ["Software Engineering"]})
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    return r.json()["job_id"]


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["database"] is True


def test_meta_config_exposes_no_secrets(client):
    body = client.get("/api/meta/config").json()
    assert "openai_api_key" not in str(body).lower()
    assert len(body["default_fields"]) == 14


@pytest.mark.parametrize("url", ["", "ftp://x.edu.cn", "http://localhost", "http://192.168.1.1"])
def test_start_rejects_invalid_urls(client, url):
    r = client.post("/api/research/start", json={"university_url": url})
    assert r.status_code == 422


def test_job_status_and_steps(client, job_id):
    job = client.get(f"/api/research/{job_id}").json()
    assert job["status"] == "completed" and job["progress"] == 100
    assert [s["key"] for s in job["steps"]] == ["university", "departments", "professors", "verification", "results"]
    assert job["university_name"] == "Mock University"
    assert job["fields"] == ["NLP", "Computer Vision", "Software Engineering"]


def test_unknown_job_404(client):
    assert client.get("/api/research/doesnotexist").status_code == 404


def test_university_endpoint(client, job_id):
    u = client.get(f"/api/research/{job_id}/university").json()
    assert u["name"] == "Mock University" and u["name_chinese"] == "模拟大学"
    assert "scholarship" not in u and "english_taught" not in u
    assert u["sources"][0]["source_url"].startswith("https://www.mocku.edu.cn")


def test_removed_endpoints_are_gone(client, job_id):
    assert client.get(f"/api/research/{job_id}/programs").status_code == 404


def test_departments(client, job_id):
    depts = client.get(f"/api/research/{job_id}/departments").json()
    assert depts and depts[0]["url"]


def test_professor_list_and_filters(client, job_id):
    base = f"/api/research/{job_id}/professors"
    allp = client.get(base).json()
    assert len(allp) >= 5
    assert set(allp[0]) >= {"name", "name_chinese", "position", "department_name", "email", "profile_url",
                            "verification_status"}
    assert "research_areas" not in allp[0] and "latest_publication" not in allp[0]
    with_email = client.get(base, params={"has_email": True}).json()
    assert with_email and all(p["email"] for p in with_email)
    q = client.get(base, params={"q": "张伟"}).json()
    assert [p["email"] for p in q] == ["zhangwei@mocku.edu.cn"]
    by_email = client.get(base, params={"q": "lina@"}).json()
    assert [p["name_chinese"] for p in by_email] == ["李娜"]
    ver = client.get(base, params={"verification": "VERIFIED"}).json()
    assert ver and all(p["verification_status"] == "VERIFIED" for p in ver)
    dept = allp[0]["department_name"]
    assert all(p["department_name"] == dept for p in client.get(base, params={"department": dept}).json())
    by_name = client.get(base, params={"sort": "name"}).json()
    assert [p["name"] for p in by_name] == sorted(p["name"] for p in by_name)


def test_professor_detail_and_email_draft(client, job_id):
    profs = client.get(f"/api/research/{job_id}/professors", params={"q": "张伟"}).json()
    pid = profs[0]["id"]
    d = client.get(f"/api/professors/{pid}").json()
    assert d["sources"] and d["verification_checks"]["email_public"] is True
    assert d["profile_url"].startswith("https://cs.mocku.edu.cn/")
    assert client.get(f"/api/professors/{pid}/publications").status_code == 404

    r = client.post(f"/api/professors/{pid}/generate-email", json={
        "student_name": "Ali Khan", "student_background": "BSc Computer Science, GPA 3.7, NLP projects.",
        "research_interest": "Natural Language Processing"})
    assert r.status_code == 200, r.text
    draft = r.json()
    assert draft["generated_by"] == "template"
    assert "Ali Khan" in draft["body"] and "Dear Professor Zhang" in draft["body"]
    assert any("Read the professor's profile" in w for w in draft["warnings"])
    assert client.get(f"/api/professors/{pid}/email-drafts").json()


@pytest.mark.parametrize("fmt,magic", [("csv", b"\xef\xbb\xbf"), ("excel", b"PK"), ("pdf", b"%PDF")])
def test_exports(client, job_id, fmt, magic):
    r = client.get(f"/api/research/{job_id}/export/{fmt}")
    assert r.status_code == 200
    assert r.content.startswith(magic)
    assert "attachment" in r.headers["content-disposition"]


def test_export_bad_format(client, job_id):
    assert client.get(f"/api/research/{job_id}/export/docx").status_code == 400


def test_results_json_shape(client, job_id):
    res = client.get(f"/api/research/{job_id}/results").json()
    assert set(res) >= {"university", "departments", "professors"}
    assert "scholarship" not in res and "programs" not in res
    p = res["professors"][0]
    assert set(p) >= {"name", "email", "profile_url", "sources", "verification_status"}


def test_access_token_enforced(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_access_token", "s3cret")
    assert client.get("/api/research").status_code == 401
    assert client.get("/api/research", headers={"X-Access-Token": "s3cret"}).status_code == 200
    assert client.get("/api/health").status_code == 200  # health stays public


def test_rate_limit(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_jobs_per_hour_per_ip", 0)
    r = client.post("/api/research/start", json={"university_url": "www.mocku.edu.cn"})
    assert r.status_code == 429
