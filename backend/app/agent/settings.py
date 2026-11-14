"""Agent runtime settings, resolved once from ``app.config`` / environment / ``.env``.

Why a separate module: the agent must keep working even while the shared
``app.config`` module is evolving (or absent in a unit-test sandbox). We therefore
try ``app.config.settings`` first and fall back to plain environment variables,
loading the repository ``.env`` with python-dotenv (which never overrides variables
already set in the process environment).

Security: the API key is held only in memory on the ``ProviderConfig`` object. It is
excluded from ``repr`` so it can never end up in logs or tracebacks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
APP_DATA_DIR = Path(__file__).resolve().parents[1] / "data"

DEFAULT_AS_OF = "2026-09-18"


def _load_dotenv() -> None:
    """Load ``<repo>/.env`` into ``os.environ`` without overriding existing values."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv is a declared dependency
        return
    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _from_app_config(name: str) -> str | None:
    """Read a setting from ``app.config.settings`` if that module exists.

    The shared config may expose either upper- or lower-case attribute names, so both
    are tried. Any import problem simply means "not available".
    """
    try:
        from app import config as app_config  # type: ignore[attr-defined]
    except Exception:
        return None
    obj = getattr(app_config, "settings", None) or getattr(app_config, "SETTINGS", None)
    for holder in (obj, app_config):
        if holder is None:
            continue
        for attr in (name, name.lower()):
            value = getattr(holder, attr, None)
            if value is not None and not callable(value):
                # pydantic SecretStr support
                if hasattr(value, "get_secret_value"):
                    value = value.get_secret_value()
                return str(value)
    return None


def env(name: str, default: str | None = None) -> str | None:
    """Resolve a setting: process env → ``app.config`` → ``.env`` file → default."""
    if name in os.environ and os.environ[name] != "":
        return os.environ[name]
    value = _from_app_config(name)
    if value not in (None, ""):
        return value
    _load_dotenv()
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _flag(name: str, default: bool) -> bool:
    raw = env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProviderConfig:
    """One OpenAI-compatible endpoint in the provider chain."""

    name: str
    base_url: str
    model: str
    api_key: str = field(repr=False)
    #: vLLM chat-template switch for hybrid reasoning models (Nemotron). Sent only
    #: to providers known to understand it, because strict servers reject unknown fields.
    supports_thinking_toggle: bool = False


@dataclass(frozen=True)
class AgentSettings:
    providers: tuple[ProviderConfig, ...]
    offline: bool
    thinking: bool
    as_of: date
    request_timeout_s: float
    first_token_timeout_s: float
    unhealthy_cooldown_s: float
    max_tool_rounds: int
    #: Pause after a single failure or a 429 without ``Retry-After`` (seconds).
    short_cooldown_s: float = 5.0
    #: Consecutive failures before the long ``unhealthy_cooldown_s`` breaker opens.
    breaker_threshold: int = 3


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    """Return cached settings. Call ``get_settings.cache_clear()`` in tests to re-read."""
    key = env("VERDA_INFERENCE_KEY") or env("LLM_API_KEY") or ""
    providers: list[ProviderConfig] = []
    for prefix, name in (("LLM_PRIMARY", "primary"), ("LLM_FALLBACK", "fallback")):
        base = env(f"{prefix}_BASE_URL")
        model = env(f"{prefix}_MODEL")
        if base and model and key:
            providers.append(
                ProviderConfig(
                    name=name,
                    base_url=base,
                    model=model,
                    api_key=env(f"{prefix}_API_KEY") or key,
                    supports_thinking_toggle="nemotron" in model.lower(),
                )
            )
    as_of_raw = env("AS_OF_DATE", DEFAULT_AS_OF) or DEFAULT_AS_OF
    try:
        as_of = date.fromisoformat(as_of_raw[:10])
    except ValueError:
        as_of = date.fromisoformat(DEFAULT_AS_OF)
    return AgentSettings(
        providers=tuple(providers),
        offline=_flag("LLM_OFFLINE", False),
        thinking=_flag("LLM_THINKING", True),
        as_of=as_of,
        request_timeout_s=float(env("LLM_TIMEOUT_S", "45") or 45),
        first_token_timeout_s=float(env("LLM_FIRST_TOKEN_TIMEOUT_S", "25") or 25),
        unhealthy_cooldown_s=float(env("LLM_UNHEALTHY_COOLDOWN_S", "60") or 60),
        max_tool_rounds=int(env("LLM_MAX_TOOL_ROUNDS", "6") or 6),
        short_cooldown_s=float(env("LLM_SHORT_COOLDOWN_S", "5") or 5),
        breaker_threshold=max(1, int(env("LLM_BREAKER_THRESHOLD", "3") or 3)),
    )
