"""Queue and task names shared across the mesh.

Services publish well known task names onto well known queues instead of
importing one another's task functions, so they stay independently deployable.
"""

from __future__ import annotations

from typing import Final

QUEUES: Final[dict[str, str]] = {
    "download": "download",
    "extract": "extract",
    "index": "index",
    "search": "search",
}


class TaskNames:
    DOWNLOAD: Final[str] = "downloader.download"
    EXTRACT: Final[str] = "extractor.extract"
    INDEX: Final[str] = "searcher.index"
    SEARCH: Final[str] = "searcher.search"
