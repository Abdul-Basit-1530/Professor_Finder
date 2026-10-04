# Professor Finder

Extract publicly listed faculty emails from Chinese university pages. The deployed app is a Vercel frontend with a
small, stateless Vercel fetch function; it does not require the Render service or PostgreSQL database.

Enter an official university URL to scan its homepage, likely faculty directories, and a limited number of professor
profiles, or paste page content when a site cannot be fetched. Copy results or download them as CSV. Results are held
in browser memory only and disappear when the tab is closed or reloaded.

> The `backend/` directory and the sections below describing its API/database are retained as legacy code and are not
> used by the frontend-only Vercel deployment. The fetch function at `frontend/api/fetch.ts` is deployed with Vercel;
> it fetches allow-listed academic sites and stores no results.

## Current deployment

Import this repository into Vercel with **Root Directory** set to `frontend`. The build command and output directory
are defined in `frontend/vercel.json`. No Render URL, database URL, or access-token environment variable is needed.

The Vercel function accepts academic domains listed in `frontend/api/fetch.ts`. It checks redirect destinations,
limits response size and request time, and does not bypass CAPTCHA or anti-bot protection. It does not render
JavaScript. If a page cannot be fetched, paste its HTML or text into the app.

## Local development

```bash
cd frontend
npm install
npx vercel dev
```

The Vercel CLI is needed locally to run the `/api/fetch` function alongside the Angular app. `ng serve` alone can
display the UI but cannot perform URL-based scans.

## Legacy backend reference

The Python service below is retained for reference, but it is not part of the current Vercel deployment.

---

The former full-stack deployment identified the university, matched research departments, and followed official
faculty directories. Its core principle remains: email addresses must appear in page content and are never guessed.

The legacy full-stack workflow:

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

1. [Current deployment](#current-deployment)
2. [Local development](#local-development)
3. [Legacy full-stack reference](#legacy-backend-reference)
4. [Current limitations](#current-limitations)

---

## Legacy architecture

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

## Legacy workflow

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

## Legacy stack

- **Frontend:** Angular 21 (standalone components, signals), TypeScript, RxJS, Bootstrap 5, Vitest
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, httpx, BeautifulSoup + lxml, Playwright, pypinyin, openpyxl, ReportLab
- **AI (optional):** OpenAI API or any OpenAI-compatible endpoint
- **Data:** PostgreSQL (SQLite for local development and tests)
- **Deploy:** Docker, docker-compose, Render blueprint, Vercel config, GitHub Actions CI

## Legacy full-stack quick start

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

## Legacy backend environment variables

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

## Legacy database

Tables: `universities`, `research_jobs`, `departments`, `professors`, `sources`, `research_results`, `page_cache`,
`email_drafts`. Each job is a snapshot. `sources` records every page a record came from (URL, type, title,
retrieval time). `page_cache` avoids re-crawling the same pages.

```bash
cd backend
alembic upgrade head                           # create/upgrade schema (PostgreSQL)
alembic revision --autogenerate -m "change"    # after editing app/models.py
```

## Legacy full-stack tests

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

## Legacy full-stack deployment

These instructions apply only if you intentionally restore the old Python service. They are not needed to deploy the
current frontend and Vercel fetch function. The legacy deployment used Render, PostgreSQL, or a single VPS.

## Legacy API

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

## Legacy verification rules

| Status | Meaning |
|---|---|
| **VERIFIED** | Name found on the professor's official profile page, the page is on the university's domain, and the email is literally present on it |
| **PARTIALLY VERIFIED** | Official profile found, but no institutional email is published on it |
| **NOT VERIFIED** | The profile page could not be loaded, or isn't on the official domain |

## Current limitations

- URL scanning is restricted to the academic host suffixes allow-listed in `frontend/api/fetch.ts`.
- The scanner follows `robots.txt`, limits request pace and page counts, and does not bypass CAPTCHA or anti-bot checks.
- It cannot render JavaScript-only pages or read addresses embedded only in images; paste the page text/HTML when available.
- Results are not saved by the app. Reloading or closing the tab clears the in-memory list; CSV download is local to your browser.
- Confirm every address and profile on the source page before contacting anyone.
