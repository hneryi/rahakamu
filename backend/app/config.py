"""Runtime configuration for the SPankkiBot backend.

Why this module exists
----------------------
Every other module (analytics, agent, routers) needs the same handful of settings:
*where the data lives*, *what "today" is* and *how to reach the LLM*. Centralising them
in one typed ``pydantic-settings`` object means:

* values come from real environment variables first and the repo-root ``.env`` second,
  so the same code runs on a laptop, in CI and in a container without edits;
* the LLM key is a :class:`~pydantic.SecretStr`, so it never shows up in ``repr()``,
  logs or tracebacks by accident (the key must never leave the server);
* "today" is pinned by ``AS_OF_DATE`` (default ``2026-09-18``). The dataset is synthetic
  and ends on 2026-09-30, so a fixed, mid-month "now" keeps every number reproducible
  and lets the demo show a month that is still in progress.

Usage::

    from app.config import settings
    settings.as_of_date      # datetime.date
    settings.data_dir        # pathlib.Path to repo-root ``data/``
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

#: ``backend/`` directory (this file is ``backend/app/config.py``).
BACKEND_DIR: Path = Path(__file__).resolve().parents[1]
#: Repository root (one level above ``backend/``) — holds ``.env`` and ``data/``.
REPO_ROOT: Path = BACKEND_DIR.parent
#: Static JSON assets shipped with the app (MCC labels, lessons, personas, benchmarks).
APP_DATA_DIR: Path = Path(__file__).resolve().parent / "data"


class Settings(BaseSettings):
    """Typed settings. Field names map 1:1 to upper-case env vars (e.g. ``AS_OF_DATE``)."""

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- data -------------------------------------------------------------------------
    as_of_date: date = Field(
        default=date(2026, 9, 18),
        description="The simulated 'today'. Every analytic ignores transactions after it.",
    )
    data_dir: Path = Field(
        default=REPO_ROOT / "data",
        description="Directory with transactions.parquet and the customer / mortgage CSVs.",
    )
    state_db: Path = Field(
        default=BACKEND_DIR / "state.db",
        description="SQLite file for user-owned state (goals, chat feedback).",
    )

    # --- LLM (consumed by app.agent) --------------------------------------------------
    verda_inference_key: SecretStr | None = None
    llm_primary_base_url: str | None = None
    llm_primary_model: str | None = None
    llm_fallback_base_url: str | None = None
    llm_fallback_model: str | None = None
    llm_timeout_s: float = 45.0

    # --- API ----------------------------------------------------------------------------
    #: Extra browser origins allowed to call the API (comma-separated or a JSON list).
    #: Production serves the web app and /api from the same origin, which needs no
    #: CORS at all, so the default is empty. Native apps send no Origin header.
    cors_origins: Annotated[list[str], NoDecode] = []
    #: Development origins: localhost and private-network addresses on any port (Expo web,
    #: a phone on the same Wi-Fi). Set to an empty string to switch it off.
    cors_origin_regex: str = (r"^https?://(localhost|127\.0\.0\.1|\[::1\]|[a-z0-9-]+\.localhost|10(\.\d{1,3}){3}"
                              r"|192\.168(\.\d{1,3}){2}|172\.(1[6-9]|2\d|3[01])(\.\d{1,3}){2})(:\d{1,5})?$")

    # --- public-demo limits (see app.limits; all per worker, 0 = off) -------------------
    chat_rate_per_ip_per_min: int = 60  # a whole demo room can sit behind one address
    chat_rate_per_customer_per_min: int = 120  # the five demo customers are shared
    feedback_rate_per_ip_per_min: int = 60
    chat_max_concurrent_llm: int = 8
    chat_queue_wait_s: float = 1.0
    chat_max_message_chars: int = 4000
    chat_max_history_messages: int = 60
    chat_max_image_bytes: int = 4_000_000
    chat_history_char_budget: int = 12_000
    max_body_bytes: int = 8_000_000
    max_goals_per_customer: int = 20
    sqlite_busy_timeout_ms: int = 5000

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a,b as well as a JSON list; * keeps the old wide-open behaviour."""
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                import json

                return json.loads(text)
            return [part.strip() for part in text.split(",") if part.strip()]
        return value

    @field_validator("data_dir", "state_db", mode="after")
    @classmethod
    def _resolve_relative(cls, value: Path) -> Path:
        """Relative paths in ``.env`` are resolved against the repo root, not the CWD,
        so ``uv run`` from ``backend/`` and pytest from anywhere agree on the data."""
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def llm_configured(self) -> bool:
        """True when a primary LLM endpoint *and* a key are configured.

        Exposed via ``GET /api/health`` as ``llm.primary``; never exposes the key itself.
        """
        key = self.verda_inference_key.get_secret_value() if self.verda_inference_key else ""
        return bool(key.strip()) and bool(self.llm_primary_base_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide cached settings instance (FastAPI-dependency friendly)."""
    return Settings()


settings: Settings = get_settings()
