"""HTTP API service."""

from __future__ import annotations

from typing import Any, cast

from celery.result import AsyncResult  # pyright: ignore[reportMissingTypeStubs]
from fastapi import FastAPI

from common.celery_app import create_app
from common.contracts import CrawlRequest
from common.queues import QUEUES, TaskNames

celery = create_app("api", QUEUES["download"], QUEUES["extract"], QUEUES["index"])
app = FastAPI(title="engsoftware API", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/crawl", status_code=202)
def crawl(request: CrawlRequest) -> dict[str, str]:
    """Queue a URL for download -> extract -> index."""
    result = cast(
        Any,
        celery.send_task(  # pyright: ignore[reportUnknownMemberType]
            TaskNames.DOWNLOAD,
            kwargs={"url": str(request.url), "tags": request.tags},
            queue=QUEUES["download"],
        ),
    )
    return {"task_id": result.id, "url": str(request.url), "status": "PENDING"}


@app.get("/tasks/{task_id}")
def task_status(task_id: str) -> dict[str, object]:
    result = cast(Any, AsyncResult(task_id, app=celery))
    return {
        "task_id": task_id,
        "status": result.state,
        "result": result.result if result.successful() else None,
    }
