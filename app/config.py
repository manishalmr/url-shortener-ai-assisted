"""
Centralized application configuration.

All tunables are environment-driven so the same codebase can run in dev
(SQLite, permissive limits) and prod-like setups (Postgres via DATABASE_URL,
tighter limits) without code changes.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Storage
    database_url: str = "sqlite:///./data/url_shortener.db"

    # Public-facing base URL used to build short links in API responses
    base_url: str = "http://localhost:8000"

    # Short code generation
    code_length: int = 7
    max_code_generation_attempts: int = 5

    # Rate limiting (best-effort, in-process token bucket; see docs/testing-and-limitations.md)
    rate_limit_create_per_minute: int = 20
    rate_limit_redirect_per_minute: int = 120

    # Redirect lookup cache (in-process LRU + TTL; see docs/architecture.md)
    cache_ttl_seconds: int = 60
    cache_max_size: int = 5000

    # Behavior
    dedup_existing_urls: bool = True
    default_expiry_days: int | None = None  # None = no expiry unless caller specifies one

    # Security
    blocklist_path: str = str(Path(__file__).resolve().parent.parent / "config" / "blocklist.txt")
    max_original_url_length: int = 2048


settings = Settings()
