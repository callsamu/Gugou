# engsoftware

Microservices scaffold: an HTTP API orchestrates a Celery pipeline of
**downloader → extractor → searcher**, with Redis as broker and Sonic
as the search engine.

```
             POST /crawl
                 │
                 ▼
          ┌────────────┐  download  ┌────────────┐  extract   ┌────────────┐  index   ┌────────────┐
          │    api     │ ─────────▶ │ downloader │ ─────────▶ │ extractor  │ ───────▶ │  searcher  │ ──▶ Sonic
          │ (FastAPI)  │   queue    │  (Celery)  │   queue    │  (Celery)  │  queue   │  (Celery)  │
          └────────────┘            └────────────┘            └────────────┘          └────────────┘
                 │                                                                          ▲
                 └──────────────────────── search task ─────────────────────────────────────┘
```

Each service is an independent Celery worker. They never import one another:
they publish well known task names (`common.queues.TaskNames`) onto well known
queues, so any stage can be replaced or scaled on its own.

Sonic indexes the text and returns only object ids; the searcher derives that id
from the URL hash and records it with the page URL and title in its own SQLite
database (`DOCUMENTS_DB_URL`). Search tasks resolve the ids back to pages, so
the API never talks to Sonic or SQLite directly.

## Layout

```
pyproject.toml            uv workspace root (dev tooling, ruff/mypy/pytest)
packages/common/          shared settings, contracts, Celery factory, Sonic client (asonic)
services/api/             FastAPI HTTP layer
services/downloader/      fetches URLs, stores raw HTML
services/extractor/       parses HTML into structured data
services/searcher/        indexes document text and answers Sonic queries
frontend/                 Preact + Tailwind search UI
Dockerfile                one image, SERVICE build arg selects the member
docker-compose.yml        redis + sonic + the four services
```

## Getting started

```bash
cp .env.example .env
uv sync --all-packages        # install the workspace
make up                      # docker compose: redis, sonic, 4 services
```

Or run the pieces locally (needs Redis and Sonic reachable at the addresses in
`.env`):

```bash
make api        # uvicorn api.main:app --reload
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
| POST   | `/crawl`          | Queue a URL: `{"url": "https://example.com"}`   |
| GET    | `/search?q=...`   | Ask the searcher for pages with URLs and titles |
| GET    | `/tasks/{id}`     | Celery task state and result                    |
| GET    | `/healthz`        | Liveness probe                                  |
| GET    | `/docs`           | OpenAPI UI                                      |

```bash
curl -X POST localhost:8000/crawl \
  -H 'content-type: application/json' \
  -d '{"url": "https://example.com"}'
```

## Configuration

All settings live in `packages/common/src/common/config.py` and are read from
the environment (see `.env.example`): `REDIS_URL`, `SONIC_HOST`, `SONIC_PORT`, `SONIC_PASSWORD`,
`RAW_STORAGE_DIR`, `DOWNLOAD_TIMEOUT`, `SEARCH_TIMEOUT`, `DOCUMENTS_DB_URL`, …

## Quality gates

```bash
make lint   # ruff check + ruff format --check + mypy
make test   # pytest
```

Tests can live in `tests/` or next to the module they cover, e.g.
`packages/common/src/common/test_db.py`; pytest collects both.
