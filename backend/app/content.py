"""Static learning content: Money Gym lessons and AI personas, localised for the API.

The JSON files in ``app/data/`` are written by content authors with every user-facing
string as ``{"en": ..., "fi": ...}``. The app should not have to know that, so this module
*flattens* them to plain strings for the requested locale (falling back to English), and —
when a ``customer_id`` is given — evaluates each lesson's ``unlock_rule`` against the
customer's own metrics. That is the pedagogical hook: the "Latte factor" lesson unlocks
because *you* make 14 small purchases a week, not because you reached level 3.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from app.config import APP_DATA_DIR

log = logging.getLogger(__name__)
SUPPORTED_LOCALES = ("en", "fi", "sv")


@lru_cache(maxsize=4)
def _load(name: str) -> Any:
    path = APP_DATA_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("%s unreadable: %s", name, exc)
        return None


def _is_localised(v: Any) -> bool:
    return isinstance(v, dict) and bool(v) and ("en" in v or "fi" in v) and all(
        isinstance(k, str) and len(k) == 2 for k in v)


def localise(value: Any, locale: str) -> Any:
    """Recursively replace ``{"en":..,"fi":..}`` dicts with the locale's value (en fallback)."""
    if _is_localised(value):
        chosen = value.get(locale, value.get("en", next(iter(value.values()))))
        return localise(chosen, locale)
    if isinstance(value, dict):
        return {k: localise(v, locale) for k, v in value.items()}
    if isinstance(value, list):
        return [localise(v, locale) for v in value]
    return value


def lesson_metrics(customer_id: str) -> dict[str, Any]:
    """Metrics referenced by lesson unlock rules, computed from the customer's data."""
    from app import db
    from app.analytics.common import as_of
    from app.analytics.goals import list_goals
    from app.analytics.profile import spender_profile
    from app.analytics.recurring import recurring_payments
    from app.analytics.safe_to_spend import safe_to_spend
    from datetime import timedelta

    cust = db.get_customer(customer_id)
    prof = spender_profile(customer_id)
    goals = list_goals(customer_id)
    min_bal = db.scalar(
        "SELECT min(balance_after_eur) FROM tx WHERE customer_id = ? AND tx_date > ?",
        [customer_id, as_of() - timedelta(days=90)],
    )
    return {
        "leak_share": prof["leak_share"],
        "savings_rate": prof["savings_rate"],
        "small_tx_per_week": prof["small_tx_per_week"],
        "late_night_share": prof["late_night_share"],
        "safe_status": safe_to_spend(customer_id)["status"],
        "min_balance_90d": float(min_bal) if min_bal is not None else 0.0,
        "recurring_leak_count": sum(1 for i in recurring_payments(customer_id)["items"]
                                    if i["basket"] == "leak"),
        "goal_count": len(goals),
        "goal_kind": [g["kind"] for g in goals],
        "age": cust["age"],
    }


def _eval_rule(rule: Any, metrics: dict[str, Any]) -> bool:
    if not isinstance(rule, dict) or rule.get("always"):
        return True
    m = metrics.get(str(rule.get("metric")))
    op, val = rule.get("op"), rule.get("value")
    if m is None:
        return False
    try:
        if op == "<":
            return m < val
        if op == "<=":
            return m <= val
        if op == ">":
            return m > val
        if op == ">=":
            return m >= val
        if op == "in":
            return m in (val or [])
        if op == "has":
            return val in (m or [])
        if op in ("==", "="):
            return m == val
    except TypeError:
        return False
    return False


def get_lessons(locale: str = "en", customer_id: str | None = None) -> dict[str, Any]:
    """Localised lessons (+ concepts). With ``customer_id`` each lesson has ``unlocked``."""
    loc = locale if locale in SUPPORTED_LOCALES else "en"
    data = _load("lessons.json")
    if not isinstance(data, dict):
        return {"locale": loc, "lessons": [], "concepts": {}, "meta": {}}
    lessons = localise(data.get("lessons", []), loc)
    if customer_id:
        metrics = lesson_metrics(customer_id)
        raw = data.get("lessons", [])
        for les, src in zip(lessons, raw, strict=False):
            les["unlocked"] = _eval_rule(src.get("unlock_rule"), metrics)
    lessons.sort(key=lambda x: (x.get("order", 999), x.get("level", 9)))
    return {"locale": loc, "lessons": lessons, "concepts": localise(data.get("concepts", {}), loc),
            "meta": localise(data.get("meta", {}), loc)}


def get_personas(locale: str | None = None) -> Any:
    """``personas.json`` as-is (or localised when ``locale`` is given)."""
    data = _load("personas.json")
    if data is None:
        return {"version": 0, "default": "sisu", "personas": []}
    return localise(data, locale) if locale else data
