"""Environment backed configuration shared by all services."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "gugou"
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "sqlite:///gugou.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    meilisearch_url: str = "http://localhost:7700"
    meilisearch_api_key: str = "SecretPassword"
    meilisearch_index: str = "pages"

    download_timeout: float = 30.0
    download_max_bytes: int = 5 * 1024 * 1024
    search_timeout: float = 10.0
    frontier_url: str = "http://localhost:8001"
    frontier_timeout: float = 10.0
    user_agent: str = "gugou-downloader/0.1"

    raw_storage_dir: str = "data/raw"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def broker_url(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
