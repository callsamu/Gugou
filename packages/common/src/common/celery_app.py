"""Celery application factory used by every service."""

from __future__ import annotations

from typing import Any, cast

from celery import Celery  # pyright: ignore[reportMissingTypeStubs]
from kombu import Queue  # pyright: ignore[reportMissingTypeStubs]

from common.config import settings


def create_app(service: str, *queues: str) -> Celery:
    """Build a Celery app bound to the given queues."""
    app = Celery(service)
    conf = cast(Any, app.conf)  # pyright: ignore[reportUnknownMemberType]
    conf.update(
        broker_url=settings.broker_url,
        result_backend=settings.result_backend,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_acks_late=True,
        worker_prefetch_multiplier=1,
        task_create_missing_queues=True,
        task_queues=[Queue(name) for name in queues],
        broker_connection_retry_on_startup=True,
    )
    return app
