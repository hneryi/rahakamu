"""Request locale for the REST layer and analytics texts (SPEC §5.6: en / fi / sv).

Why a context variable
----------------------
Analytics functions produce a few human sentences (safe-to-spend explanation, nudges,
survival tips, basket "why" texts, merchant labels…). Threading a ``locale`` argument
through every function — and through the memoisation layer — would touch every
signature in :mod:`app.analytics`. Instead the *current locale* lives in a
:class:`contextvars.ContextVar`:

* :class:`LocaleMiddleware` sets it from ``?locale=`` on every HTTP request (unknown or
  missing values fall back to English, never an error);
* the agent's ``execute_tool`` sets it from the chat turn language;
* text-producing code calls :func:`tr` / :func:`loc`, and
  :func:`app.analytics.cache.ledger_cache` includes the locale in its cache key.

Context variables follow the request into FastAPI's thread pool and ``asyncio.to_thread``
(both copy the context), so the value is per request, never global.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, TypeVar
from urllib.parse import parse_qs

from app.agent.lang import DEFAULT_LOCALE, LOCALES, norm_locale
from app.agent.vocab import fmt_eur

__all__ = ["LOCALES", "LocaleMiddleware", "day", "eur", "loc", "norm_locale", "tr", "use_locale"]

T = TypeVar("T")

_current: ContextVar[str] = ContextVar("spankkibot_locale", default=DEFAULT_LOCALE)


def loc() -> str:
    """The locale of the current request / tool call (``en`` / ``fi`` / ``sv``)."""
    return _current.get()


def tr(en: T, fi: T, sv: T) -> T:
    """Pick the variant for the current locale."""
    current = _current.get()
    return fi if current == "fi" else sv if current == "sv" else en


def eur(value: float | int | None, decimals: int | None = None) -> str:
    """Money in the current locale's format: ``1,234.50 €`` / ``1 234,50 €``."""
    return fmt_eur(value, loc(), decimals)


def day(value: object) -> str:
    """A date for prose: ISO in English (unchanged API text), ``25.9.2026`` in fi / sv."""
    from datetime import date

    d = value if isinstance(value, date) else None
    if d is None:
        try:
            d = date.fromisoformat(str(value)[:10])
        except ValueError:
            return str(value)
    return d.isoformat() if loc() == "en" else f"{d.day}.{d.month}.{d.year}"


@contextmanager
def use_locale(locale: object) -> Iterator[str]:
    """Temporarily set the current locale (normalised; unknown → ``en``)."""
    token = _current.set(norm_locale(locale))
    try:
        yield _current.get()
    finally:
        _current.reset(token)


class LocaleMiddleware:
    """Pure ASGI middleware: ``?locale=sv`` → current locale for the whole request."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))
        with use_locale((query.get("locale") or [DEFAULT_LOCALE])[0]):
            await self.app(scope, receive, send)
