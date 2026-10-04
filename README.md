# China University Professor Research Agent ("Professor Finder")

A web application that helps students find supervisors at Chinese universities (for example, for a Chinese
Government Scholarship application). You give it an official university website and your research fields. It then:

1. identifies the university (English and Chinese name, location),
2. finds the **schools and departments that match your fields** (e.g. 计算机学院 for Computer Science / AI),
3. walks their official faculty directories and lists **every professor** with:
   - name (English + Chinese), position and department
   - their **publicly listed institutional email**
   - their **official profile link**
   - a **verification status** and the source pages

You can then search and filter the list, copy all the emails, export the results to CSV, Excel or PDF, and write an
editable supervision-request email.

> **Core principle: no guessing.** Every email must literally appear on the professor's official page; it is never
> built from a naming pattern. An optional LLM only reads pages that were actually fetched, and anything it returns
> is re-checked against the page text. If an email isn't published, the app shows **"Not publicly listed"**.

---

## Contents

1. [Architecture](#architecture)
2. [Workflow](#workflow)
3. [Tech stack](#tech-stack)
4. [Quick start (local)](#quick-start-local)
5. [Environment variables](#environment-variables)
6. [Database](#database)
7. [Running tests](#running-tests)
8. [Deployment](#deployment)
9. [API](#api)
10. [Verification rules](#verification-rules)
11. [Limitations & responsible use](#limitations--responsible-use)

---

## Architecture

```
┌────────────────────┐   /api (same origin via proxy)   ┌──────────────────────────────────────────┐
│  Angular 21 SPA    │ ───────────────────────────────▶ │  FastAPI                                 │
│  (Vercel / nginx)  │ ◀── JSON, CSV/XLSX/PDF ───────── │  ├─ REST API (validation, auth, limits)  │
└────────────────────┘                                  │  ├─ Job runner (thread pool, DB-backed)  │
                                                        │  └─ Research workflow                    │
                                                        │       ├─ University Discovery            │
                                                        │       ├─ Department Discovery            │
                                                        │       ├─ Professor Discovery             │
                                                        │       └─ Verification                    │
                                                        │  Services: Fetcher (robots, rate limit,  │
                                                        │  cache, Playwright) · LLM (optional)     │
                                                        └──────────────┬───────────────────────────┘
                                                                       │ SQLAlchemy
                                                                ┌──────▼──────┐
                                                                │ PostgreSQL  │
                                                                └─────────────┘
```

| Decision | Why |
|---|---|
| **Background jobs** (`POST /start` → `job_id`, then poll) | A crawl takes 1–3 minutes. Jobs run on a bounded thread pool and write progress to the database, so the page can show live progress. |
| **Async `httpx` + BeautifulSoup**, **Playwright** as fallback | Fast, polite fetching with per-host rate limits. Playwright renders pages whose faculty lists or emails are filled in by JavaScript, which is common on Chinese faculty systems. |
| **Heuristics first, LLM optional** | Deterministic parsers (Chinese name detection, email regex including `name#domain` forms, bilingual department matching) do the work. An LLM only helps pick links or read awkward pages, and is grounding-checked. |
| **Same-origin `/api`** | The frontend contains no backend URL and no secrets. |

## Workflow

```
Enter URL + fields ─▶ University ─▶ Relevant departments ─▶ Faculty directories ─▶ Profiles ─▶ Verify ─▶ List
```

1. **University:** fetches the homepage (and the English site if linked) and reads the official name and address.
2. **Departments:** opens the schools index (院系设置 / 学院部门 / Schools) and scores each school against your fields in English and Chinese (`计算机`, `软件`, `人工智能`, …). It prefers department homepages on their own subdomain and ignores news links, off-site redirects and non-academic units.
3. **Professors:** follows each department's faculty directory (师资队伍 / 教师名录 / Faculty), including pagination and 教授/副教授 tabs, then opens each profile. It reads the name, position and email:
   - Emails written as `name#domain`, `name [at] domain` or `mailto:` links are recognised.
   - Office and footer emails (e.g. `cs@…`) are excluded.
   - When a profile has an email field but the address is filled in by JavaScript, the page is rendered in a browser (Playwright) and read again.
4. **Verification:** re-checks every email against the page text, removes duplicates (the same professor on Chinese and English pages), and lists verified contacts first.

**Chinese names:** names are romanised with pinyin ("张伟" → "Zhang Wei"). Characters with genuinely ambiguous readings (e.g. 曾 Zeng/Ceng) keep the Chinese name only, and English names written on the page always win.

## Tech stack

- **Frontend:** Angular 21 (standalone components, signals), TypeScript, RxJS, Bootstrap 5, Vitest
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, httpx, BeautifulSoup + lxml, Playwright, pypinyin, openpyxl, ReportLab
- **AI (optional):** OpenAI API or any OpenAI-compatible endpoint
- **Data:** PostgreSQL (SQLite for local development and tests)
- **Deploy:** Docker, docker-compose, Render blueprint, Vercel config, GitHub Actions CI

## Quick start (local)

Prerequisites: Python 3.12+, Node.js 22+ (or 24.15+).

```bash
# 1. Backend
cd backend
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pip install playwright && playwright install chromium   # recommended (JavaScript-rendered emails)
cp ../.env.example .env              # set PLAYWRIGHT_ENABLED=true; OPENAI_API_KEY optional
uvicorn app.main:app --reload --port 8000               # API docs: http://localhost:8000/docs

# Optional: offline demo data (runs the real workflow against the bundled mock university)
python -m scripts.seed_demo

# 2. Frontend (new terminal)
cd frontend
npm install
npm start                            # http://localhost:4200  (proxies /api → :8000)
```

**Everything in Docker** (PostgreSQL + backend with Playwright + nginx frontend):

```bash
cp .env.example .env
docker compose up --build            # http://localhost:8080
```

## Environment variables

All secrets stay server-side. See [`.env.example`](.env.example) for every option.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./research_agent.db` | PostgreSQL in production (`postgres://` URLs accepted) |
| `AUTO_CREATE_TABLES` | `true` | Set `false` when using Alembic (Docker does) |
| `PLAYWRIGHT_ENABLED` | `false` | **Recommended `true`.** Renders JavaScript faculty lists and emails |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `LLM_MODEL` | — / — / `gpt-4.1-mini` | Optional AI help for unusual page layouts |
| `MAX_PROFESSORS` / `MAX_DEPARTMENTS` | `40` / `5` | Limits per job (users can change max professors per search) |
| `ALLOW_NON_INSTITUTIONAL_EMAILS` | `false` | Also show personal emails (e.g. `@163.com`, `@sina.com`) listed on official profiles |
| `MAX_PAGES_PER_JOB` | `200` | Crawl budget per job |
| `REQUEST_DELAY_SECONDS` | `1.0` | Per-host politeness delay |
| `RESPECT_ROBOTS_TXT` | `true` | Obey robots.txt |
| `CACHE_TTL_HOURS` | `72` | Page cache lifetime (users can force a fresh crawl) |
| `SEARCH_PROVIDER` / `SEARCH_API_KEY` | `none` | Optional fallback for finding departments: `serper`, `brave`, `tavily`, `searxng` |
| `DEFAULT_FIELDS` | 14 CS fields | Comma-separated default research fields |
| `CORS_ORIGINS` | `http://localhost:4200` | Allowed frontend origins |
| `APP_ACCESS_TOKEN` | — | Optional shared token required on `/api/*` (entered under Settings) |
| `MAX_JOBS_PER_HOUR_PER_IP` / `MAX_CONCURRENT_JOBS` | `20` / `2` | Abuse protection / parallel jobs |

## Database

Tables: `universities`, `research_jobs`, `departments`, `professors`, `sources`, `research_results`, `page_cache`,
`email_drafts`. Each job is a snapshot. `sources` records every page a record came from (URL, type, title,
retrieval time). `page_cache` avoids re-crawling the same pages.

```bash
cd backend
alembic upgrade head                           # create/upgrade schema (PostgreSQL)
alembic revision --autogenerate -m "change"    # after editing app/models.py
```

## Running tests

```bash
cd backend && pytest -q                       # 72 tests, fully offline
cd frontend && npx ng test --watch=false      # 9 tests (Vitest)
```

The backend suite runs the **whole workflow against a mock Chinese university** (`backend/tests/mock_site.py`). The
mock site deliberately includes GBK-encoded pages, `name#domain` and `[at]` emails, footer office emails,
paginated directories, a duplicate English profile, a broken profile link, a gmail-only professor, an ambiguous
name romanisation and a robots.txt-blocked path. The tests check that:

- emails are never invented, including a fake LLM that returns fabricated ones
- emails rendered by JavaScript are found
- duplicates are merged
- unneeded pages are never crawled
- exports, every API endpoint, access-token auth and rate limiting work

## Deployment

**Render (backend + PostgreSQL):** push to GitHub → Render → *New Blueprint* → pick the repo
([`render.yaml`](render.yaml)). Set `CORS_ORIGINS` to your frontend URL. To enable JavaScript rendering, add
`INSTALL_PLAYWRIGHT=true` (used as a Docker build arg) and set `PLAYWRIGHT_ENABLED=true`.

**Vercel (frontend):** import the repo with root directory `frontend`. In [`frontend/vercel.json`](frontend/vercel.json)
replace `YOUR-BACKEND.onrender.com` with your backend host.

**Single VPS:** `docker compose up -d --build` and put a TLS proxy (Caddy/Traefik) in front.

## API

Interactive docs at `/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/research/start` | Start a job (`university_url`, `fields`, `custom_fields`, `max_professors`, `force_refresh`) |
| `GET` | `/api/research` | Recent jobs |
| `GET` | `/api/research/{job_id}` | Status, progress, steps, warnings |
| `POST` | `/api/research/{job_id}/cancel` | Cancel a job |
| `GET` | `/api/research/{job_id}/university` | University name, location, sources |
| `GET` | `/api/research/{job_id}/departments` | Relevant schools/departments with faculty-list links |
| `GET` | `/api/research/{job_id}/professors` | Professor list. Filters: `department, verification, has_email, q, sort` |
| `GET` | `/api/research/{job_id}/results` | Full JSON result |
| `GET` | `/api/research/{job_id}/export/{csv\|excel\|pdf}` | Downloads |
| `GET` | `/api/professors/{id}` | Professor detail + verification checks + sources |
| `POST` | `/api/professors/{id}/generate-email` | Editable draft (never sent) |
| `GET` | `/api/health`, `/api/meta/config` | Health and public config |

## Verification rules

| Status | Meaning |
|---|---|
| **VERIFIED** | Name found on the professor's official profile page, the page is on the university's domain, and the email is literally present on it |
| **PARTIALLY VERIFIED** | Official profile found, but no institutional email is published on it |
| **NOT VERIFIED** | The profile page could not be loaded, or isn't on the official domain |

## Limitations & responsible use

- Some Chinese university sites protect pages with **anti-bot checks that reject automated browsers**. The app never tries to evade them; it lists those pages by name so you can open them yourself.
- Emails shown only as images can't be read and are reported as "Not publicly listed".
- Without an OpenAI key, the app relies on heuristics, which work well on conventional faculty directories.
- Crawling is deliberately polite: it follows robots.txt, adds per-host delays, has a page budget and caches pages. Please keep it that way.
- Always open a professor's profile before writing to them. Email drafts are never sent automatically.
