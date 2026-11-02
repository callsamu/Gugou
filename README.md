# Gugou

Microservices scaffold: an HTTP API feeds a URL frontier, which drives a
Celery pipeline of **downloader → extractor → searcher**, with Redis as broker,
Meilisearch as the search engine and one shared SQLite database.

```
             POST /crawl
                 │
                 ▼
          ┌────────────┐  add URL   ┌────────────┐  download  ┌────────────┐  extract   ┌────────────┐  index   ┌────────────┐
          │    api     │ ─────────▶ │  frontier  │ ─────────▶ │ downloader │ ─────────▶ │ extractor  │ ───────▶ │  searcher  │ ──▶ Meilisearch
          │ (FastAPI)  │   HTTP     │ (FastAPI)  │   queue    │  (Celery)  │   queue    │  (Celery)  │  queue   │  (Celery)  │
          └────────────┘            └────────────┘            └────────────┘            └────────────┘          └────────────┘
                 │                                                                          ▲
                 └──────────────────────── search task ─────────────────────────────────────┘
```

The searcher stores each page in Meilisearch and answers search tasks with ranked
hits. The API never talks to Meilisearch directly.

Each service is independently deployable. Celery workers publish well-known task
names (`common.queues.TaskNames`) onto well-known queues, so any stage can be
replaced or scaled on its own.

The frontier owns the `frontier_url` table and an in-memory priority queue
ordered by insertion time. It sends one download task at a time and records each
URL as pending, completed or failed. URLs from the same origin are scheduled 15
seconds apart.

Before fetching a page, the downloader fetches and caches the origin's
robots.txt and skips URLs disallowed for its user agent.

After extracting a page, the extractor records its content hash in the
`extractor_content` table, resolves the links it found and sends them back to the
frontier over HTTP. It extracts text from `<article>` or `<main>` when present,
ignoring header, nav, aside and footer chrome. The page title and meta
description are captured separately.

The frontier and extractor share `DATABASE_URL`. Their tables are namespaced by
service so one SQLite file can hold both without collisions. Before forwarding
links, the extractor filters them through a small in-memory Bloom filter of URLs
it has already sent, so duplicates do not trigger frontier database lookups.

## Layout

```
pyproject.toml            uv workspace root (dev tooling, ruff/mypy/pytest)
packages/common/          shared settings, contracts, Celery factory, Meilisearch client
services/api/             FastAPI HTTP layer
services/frontier/        URL table, priority queue and download dispatch
services/downloader/      fetches URLs, stores raw HTML
services/extractor/       content table, parses HTML and forwards found links
services/searcher/        indexes document text and answers Meilisearch queries
frontend/                 Preact + Tailwind search UI
Dockerfile                one image, SERVICE build arg selects the member
frontend/Dockerfile       multi-stage Preact build served by nginx on Alpine
docker-compose.yml        redis + meilisearch + the five services + frontend
```

## Getting started

```bash
cp .env.example .env
uv sync --all-packages        # install the workspace
make up                      # docker compose: redis, meilisearch, 5 services, frontend
```

The stack includes the frontend at http://localhost:3000 (nginx on Alpine).

Or run the pieces locally (needs Redis and Meilisearch reachable at the addresses
in `.env`):

```bash
make api        # uvicorn api.main:app --reload
make frontier   # uvicorn frontier.main:app --reload --port 8001
make frontend   # Vite dev server on http://localhost:5173
make downloader # celery -A downloader.main:app worker -Q download
make extractor  # celery -A extractor.main:app worker -Q extract
make searcher   # celery -A searcher.main:app worker -Q index,search
```

The `/crawl` page adds seed URLs, pauses/resumes the frontier queue, and lists
stored URLs with status, priority and creation-time filters.

The frontend talks to the API at `http://localhost:8000` by default. Set
`VITE_API_URL` in `.env` (or the environment) when building the container or
running the dev server against another host:

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

## API

| Method | Path              | Description                                     |
| ------ | ----------------- | ----------------------------------------------- |
| POST   | `/crawl`          | Add a URL to the frontier: `{"url": "https://example.com"}` |
| GET    | `/urls`           | List stored URLs; filter by `status`, order by `priority`/`createdAt` |
| GET    | `/queue`          | Return whether frontier queue consumption is paused |
| POST   | `/pause`          | Pause frontier queue consumption                |
| POST   | `/resume`         | Resume frontier queue consumption               |
| GET    | `/search?q=...`   | Ask the searcher for pages with URLs and titles |
| GET    | `/tasks/{id}`     | Celery task state and result                    |
| GET    | `/healthz`        | Liveness probe                                  |
| GET    | `/docs`           | OpenAPI UI                                      |

```bash
curl -X POST localhost:8000/crawl \
  -H 'content-type: application/json' \
  -d '{"url": "https://example.com"}'
```

The frontier exposes its own small HTTP API on port 8001:

| Method | Path       | Description                                           |
| ------ | ---------- | ----------------------------------------------------- |
| GET    | `/urls`    | List stored URLs; `status`, `order_by`, `order`, `limit`, `offset` |
| POST   | `/urls`    | Add URLs; `force: true` re-queues already-seen URLs   |
| GET    | `/queue`   | Queue pause state                                     |
| POST   | `/pause`   | Pause queue consumption; new URLs are still accepted  |
| POST   | `/resume`  | Resume queue consumption                              |
| GET    | `/healthz` | Liveness probe                                        |

## Configuration

All settings live in `packages/common/src/common/config.py` and are read from
the environment (see `.env.example`): `REDIS_URL`, `MEILISEARCH_URL`,
`MEILISEARCH_API_KEY`, `MEILISEARCH_INDEX`, `RAW_STORAGE_DIR`, `DOWNLOAD_TIMEOUT`,
`SEARCH_TIMEOUT`, `FRONTIER_URL`, `DATABASE_URL`, … The frontier and extractor
share `DATABASE_URL` and own separate tables (`frontier_url` and
`extractor_content`).

## Quality gates

```bash
make lint   # ruff check + ruff format --check + mypy
make test   # pytest
```

Tests can live in `tests/` or next to the module they cover, e.g.
`packages/common/src/common/test_db.py`; pytest collects both.
