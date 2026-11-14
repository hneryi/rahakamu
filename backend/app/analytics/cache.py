"""Memoisation for pure ledger analytics.

The ledger is immutable for a given ``AS_OF_DATE`` (the ``tx`` table is a read-only,
content-addressed cache), so any analytic that depends *only* on the ledger — not on
user-owned state such as goals — returns the same answer for the same arguments for the
lifetime of the process. Memoising those functions turns the home screen's repeated
sub-computations (payday, recurring bills, monthly averages…) into dictionary lookups.

Results are deep-copied on the way out so a caller mutating a returned dict can never
corrupt the cache. Functions that read goals (safe-to-spend, goal planning, nudges,
overview) are intentionally *not* memoised.

Some results contain short human texts (labels, explanations) in the request locale
(:mod:`app.i18n`), so the current locale is part of the cache key.
"""

from __future__ import annotations

import copy
import functools
from collections.abc import Callable
from typing import Any, TypeVar, cast

F = TypeVar("F", bound=Callable[..., Any])


def ledger_cache(maxsize: int = 4096) -> Callable[[F], F]:
    """LRU-cache a pure ledger function; returns deep copies of cached values."""

    def deco(fn: F) -> F:
        @functools.lru_cache(maxsize=maxsize)
        def cached(locale: str, *args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            from app.i18n import loc

            try:
                value = cached(loc(), *args, **kwargs)
            except TypeError:  # unhashable argument (e.g. a list): just compute
                return fn(*args, **kwargs)
            return copy.deepcopy(value)

        wrapper.cache_clear = cached.cache_clear  # type: ignore[attr-defined]
        return cast(F, wrapper)

    return deco
