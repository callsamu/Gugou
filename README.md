# engsoftware

Microservices scaffold: an HTTP API feeds a URL frontier, which drives a
Celery pipeline of **downloader → extractor → searcher**, with Redis as broker
and Sonic as the search engine.

```
             POST /crawl
                 │
                 ▼
          ┌────────────┐  add URL   ┌────────────┐  download  ┌────────────┐  extract   ┌────────────┐  index   ┌────────────┐
          │    api     │ ─────────▶ │  frontier  │ ─────────▶ │ downloader │ ─────────▶ │ extractor  │ ───────▶ │  searcher  │ ──▶ Sonic
          │ (FastAPI)  │   HTTP     │ (FastAPI)  │   queue    │  (Celery)  │   queue    │  (Celery)  │  queue   │  (Celery)  │
          └────────────┘            └────────────┘            └────────────┘            └────────────┘          └────────────┘
                 │                                                                          ▲
                 └──────────────────────── search task ─────────────────────────────────────┘
```

Each service is independently deployable. Celery workers publish well-known task
names (`common.queues.TaskNames`) onto well-known queues, so any stage can be
replaced or scaled on its own.

The frontier owns the URL database and an in-memory FIFO queue. It sends one
download task at a time and records each URL as pending, completed or failed.

Sonic indexes the text and returns only object ids; the searcher derives that id
from the URL hash and records it with the page URL and title in its own SQLite
database (`DOCUMENTS_DB_URL`). Search tasks resolve the ids back to pages, so
the API never talks to Sonic or SQLite directly.

After extracting a page, the extractor resolves the links it found and sends
them back to the frontier over HTTP.

## Layout

```
pyproject.toml            uv workspace root (dev tooling, ruff/mypy/pytest)
packages/common/          shared settings, contracts, Celery factory, Sonic client (asonic)
services/api/             FastAPI HTTP layer
services/frontier/        URL database, FIFO queue and download dispatch
services/downloader/      fetches URLs, stores raw HTML
services/extractor/       parses HTML, sends discovered links to the frontier
services/searcher/        indexes document text and answers Sonic queries
frontend/                 Preact + Tailwind search UI
Dockerfile                one image, SERVICE build arg selects the member
docker-compose.yml        redis + sonic + the five services
```

## Getting started

```bash
cp .env.example .env
uv sync --all-packages        # install the workspace
make up                      # docker compose: redis, sonic, 5 services
```

Or run the pieces locally (needs Redis and Sonic reachable at the addresses in
`.env`):

```bash
make api        # uvicorn api.main:app --reload
make frontier   # uvicorn frontier.main:app --reload --port 8001
make frontend   # Vite dev server on http://localhost:5173
make downloader # celery -A downloader.main:app worker -Q download
make extractor  # celery -A extractor.main:app worker -Q extract
make searcher   # celery -A searcher.main:app worker -Q index,search
```

The frontend talks to the API at `http://localhost:8000` by default. Set
`VITE_API_URL` when building or running it against another host:

```bash
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev
```

## API

| Method | Path              | Description                                     |
| ------ | ----------------- | ----------------------------------------------- |
| POST   | `/crawl`          | Add a URL to the frontier: `{"url": "https://example.com"}` |
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
| POST   | `/urls`    | Add URLs: `{"urls": ["https://example.com"]}`         |
| GET    | `/healthz` | Liveness probe                                        |

## Configuration

All settings live in `packages/common/src/common/config.py` and are read from
the environment (see `.env.example`): `REDIS_URL`, `SONIC_HOST`, `SONIC_PORT`, `SONIC_PASSWORD`,
`RAW_STORAGE_DIR`, `DOWNLOAD_TIMEOUT`, `SEARCH_TIMEOUT`, `DOCUMENTS_DB_URL`,
`FRONTIER_URL`, `FRONTIER_DB_URL`, …

## Quality gates

```bash
make lint   # ruff check + ruff format --check + mypy
make test   # pytest
```

Tests can live in `tests/` or next to the module they cover, e.g.
`packages/common/src/common/test_db.py`; pytest collects both.
