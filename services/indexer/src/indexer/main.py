"""Search indexer worker (Sonic)."""

from __future__ import annotations

import hashlib
from typing import Any, cast

from common.celery_app import create_app
from common.config import settings
from common.contracts import Extracted
from common.queues import QUEUES, TaskNames
from common.sonic import SonicIngest

app = create_app("indexer", QUEUES["index"])


@cast(Any, app.task)(name=TaskNames.INDEX)  # pyright: ignore[reportUnknownMemberType]
def index(payload: dict[str, Any]) -> dict[str, Any]:
    """Push the document text to Sonic.

    Sonic only returns object ids on search, so ``id`` maps back to the URL
    (or to a document id in whatever store you add later).
    """
    document = Extracted.model_validate(payload)
    doc_id = hashlib.sha256(document.url.encode()).hexdigest()[:16]
    text = "\n".join(part for part in (document.title, document.text) if part)

    with SonicIngest(settings.sonic_host, settings.sonic_port, settings.sonic_password) as sonic:
        sonic.push(settings.sonic_collection, settings.sonic_bucket, doc_id, text)

    return {
        "id": doc_id,
        "collection": settings.sonic_collection,
        "bucket": settings.sonic_bucket,
        "url": document.url,
    }
