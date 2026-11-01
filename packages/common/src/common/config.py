"""Environment backed configuration shared by all services."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "engsoftware"
    debug: bool = False
    log_level: str = "INFO"

    downloader_db_url: str = "sqlite:///downloader.db"
    extractor_db_url: str = "sqlite:///extractor.db"
    documents_db_url: str = "sqlite:///documents.db"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    sonic_host: str = "localhost"
    sonic_port: int = 1491
    sonic_password: str = "SecretPassword"
    sonic_collection: str = "web-pages"
    sonic_bucket: str = "pages"

    download_timeout: float = 30.0
    download_max_bytes: int = 5 * 1024 * 1024
    search_timeout: float = 10.0
    user_agent: str = "obuscador-downloader/0.1"

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
