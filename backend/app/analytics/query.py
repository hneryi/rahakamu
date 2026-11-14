"""The MyData engine: flexible, *safe* questions over the customer's own ledger.

Why
---
Users ask open-ended questions ("How much did I spend on taxis last month?", "Which
weekday do I eat out most?"). Letting an LLM write SQL would be powerful but unsafe and
unauditable. Instead the agent fills in a small, typed filter object and this module turns
it into **fully parameterised SQL**:

* filters (dates, category, basket, merchant, MCC, amount range, free text) are bound
  parameters — never string-formatted;
* ``group_by`` is looked up in a whitelist (:data:`GROUP_BY_SQL`); anything else raises;
* the customer id is always the first predicate, so a query can never see another
  customer's rows (privacy by construction).

Results are aggregates the LLM can quote verbatim and the app can chart directly.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app import db
from app.analytics.common import (
    ALL_BASKETS,
    BASKET_LABELS,
    basket_label,
    TX_SELECT,
    as_of,
    month_label,
    parse_date,
    r2,
    tx_to_dict,
)
from app.analytics.labels import category_label_l10n, merchant_label
from app.i18n import loc, tr

#: whitelisted group_by → (SQL key expression, is chronological)
GROUP_BY_SQL: dict[str, tuple[str | None, bool]] = {
    "none": (None, False),
    "category": ("category", False),
    "basket": ("basket", False),
    "month": ("strftime(tx_date, '%Y-%m')", True),
    "week": ("strftime(date_trunc('week', tx_date), '%Y-%m-%d')", True),
    "weekday": ("CAST(isodow(tx_date) AS VARCHAR)", True),
    "merchant": ("coalesce(merchant_id, 'cat:' || category)", False),
    "hour": ("lpad(CAST(hour(tx_timestamp) AS VARCHAR), 2, '0')", True),
    "day": ("strftime(tx_date, '%Y-%m-%d')", True),
}
DIRECTIONS = ("out", "in", "all")
DEFAULT_WINDOW_DAYS = 90
_CATEGORIES_CACHE: list[str] = []


def known_categories() -> list[str]:
    """Distinct categories in the data (cached)."""
    if not _CATEGORIES_CACHE:
        _CATEGORIES_CACHE.extend(r["category"] for r in db.query(
            "SELECT DISTINCT category FROM tx ORDER BY 1"))
    return _CATEGORIES_CACHE


def _norm_category(category: str | list[str] | None) -> list[str] | None:
    """Case-insensitive category match; accepts a list or comma-separated string."""
    if category is None or category == "" or category == []:
        return None
    items = category if isinstance(category, list) else str(category).split(",")
    lookup = {c.lower(): c for c in known_categories()}
    aliases = {"dining": "Restaurants", "eating out": "Restaurants", "food": "Groceries",
               "transport": "Transportation", "rent": "Housing", "shopping": "Lifestyle"}
    out: list[str] = []
    for raw in items:
        k = raw.strip().lower()
        if not k:
            continue
        name = lookup.get(k) or aliases.get(k)
        if name is None:
            raise ValueError(f"Unknown category '{raw}'. Known: {', '.join(known_categories())}")
        out.append(name)
    return out or None


def _norm_basket(basket: str | None) -> str | None:
    if basket is None or basket == "":
        return None
    b = basket.strip().lower()
    if b not in ALL_BASKETS:
        raise ValueError(f"Unknown basket '{basket}'. Use one of {', '.join(ALL_BASKETS)}")
    return b


def _build_where(customer_id: str, start: date, end: date, category: list[str] | None,
                 basket: str | None, merchant: str | None, mcc: int | None,
                 direction: str = "all", min_amount: float | None = None,
                 max_amount: float | None = None, text: str | None = None,
                 exclude_saving_default: bool = False) -> tuple[str, list[Any]]:
    """WHERE clause + params. Every value is a bound parameter."""
    where = ["customer_id = ?", "tx_date BETWEEN ? AND ?"]
    params: list[Any] = [customer_id, start, end]
    if category:
        where.append(f"category IN ({', '.join('?' * len(category))})")
        params.extend(category)
    if basket:
        where.append("basket = ?")
        params.append(basket)
    elif exclude_saving_default and not category:
        # "spending" means consumption: moving money to savings is not spending.
        where.append("basket IN ('fixed', 'irregular', 'leak')")
    if merchant:
        where.append("upper(merchant_id) = upper(?)")
        params.append(merchant.strip())
    if mcc is not None:
        where.append("mcc_code = ?")
        params.append(int(mcc))
    if direction == "out":
        where.append("tx_amount_eur < 0")
    elif direction == "in":
        where.append("tx_amount_eur > 0")
    if min_amount is not None:
        where.append("abs(tx_amount_eur) >= ?")
        params.append(float(min_amount))
    if max_amount is not None:
        where.append("abs(tx_amount_eur) <= ?")
        params.append(float(max_amount))
    if text:
        # Free text matches category, merchant id or transaction type (labels are derived).
        where.append("(category ILIKE ? OR coalesce(merchant_id, '') ILIKE ? "
                     "OR transaction_type ILIKE ?)")
        like = f"%{text.strip()}%"
        params.extend([like, like, like])
    return " AND ".join(where), params


def _period(start: str | date | None, end: str | date | None,
            default_days: int | None) -> tuple[date, date]:
    today = as_of()
    e = min(parse_date(end) or today, today)
    if start is not None and start != "":
        s = parse_date(start)
        assert s is not None
    elif default_days is None:
        s = date(2000, 1, 1)
    else:
        s = e - timedelta(days=default_days - 1)
    if s > e:
        raise ValueError("start must be on or before end")
    return s, e


_WEEKDAYS = {
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
    "fi": ("ma", "ti", "ke", "to", "pe", "la", "su"),
    "sv": ("mån", "tis", "ons", "tor", "fre", "lör", "sön"),
}


def _label(group_by: str, key: str, sample: dict[str, Any] | None = None) -> str:
    """Display label of a group in the current locale (the stable ``key`` is returned too)."""
    if group_by == "basket":
        return basket_label(key)
    if group_by == "category":
        return category_label_l10n(key) or key
    if group_by == "month":
        return month_label(key)
    if group_by == "week":
        return tr(f"Week of {key}", f"Viikko alkaen {key}", f"Veckan från {key}")
    if group_by == "weekday":
        return _WEEKDAYS[loc()][int(key) - 1]
    if group_by == "hour":
        return f"{key}:00"
    if group_by == "merchant":
        if key.startswith("cat:"):
            return f"{category_label_l10n(key[4:]) or key[4:]} ({tr('no merchant id', 'ei kauppiastunnusta', 'ingen handlare')})"
        mcc = sample.get("mcc") if sample else None
        cat = sample.get("category") if sample else None
        return merchant_label(key, mcc, cat)
    return key


def query_spending(customer_id: str, start: str | date | None = None, end: str | date | None = None,
                   category: str | list[str] | None = None, basket: str | None = None,
                   merchant: str | None = None, mcc: int | None = None, group_by: str = "none",
                   direction: str = "out", top_n: int = 20) -> dict[str, Any]:
    """Aggregate the customer's transactions with optional filters and grouping.

    Defaults: last 90 days up to as-of, money out (``direction="out"``) excluding saving
    transfers unless ``basket="saving"`` or a category is requested. Totals are positive
    for ``out``/``in``; for ``all`` they are the signed net.
    """
    db.ensure_customer(customer_id)
    if group_by not in GROUP_BY_SQL:
        raise ValueError(f"group_by must be one of {', '.join(GROUP_BY_SQL)}")
    if direction not in DIRECTIONS:
        raise ValueError(f"direction must be one of {', '.join(DIRECTIONS)}")
    top_n = max(1, min(int(top_n or 20), 400))
    s, e = _period(start, end, DEFAULT_WINDOW_DAYS)
    cats = _norm_category(category)
    bsk = _norm_basket(basket)
    where, params = _build_where(customer_id, s, e, cats, bsk, merchant, mcc, direction,
                                 exclude_saving_default=direction == "out")
    sign = "-" if direction == "out" else ""
    value = f"{sign}tx_amount_eur" if direction != "all" else "tx_amount_eur"

    tot = db.query_one(f"SELECT coalesce(sum({value}), 0) AS total, count(*) AS n FROM tx WHERE {where}",
                       params) or {"total": 0, "n": 0}
    total, count = float(tot["total"]), int(tot["n"])
    groups: list[dict[str, Any]] = []
    key_sql, chrono = GROUP_BY_SQL[group_by]
    if key_sql:
        rows = db.query(
            f"SELECT {key_sql} AS k, sum({value}) AS total, count(*) AS n, "
            f"any_value(mcc_code) AS mcc, any_value(category) AS category "
            f"FROM tx WHERE {where} GROUP BY k "
            + ("ORDER BY k" if chrono else "ORDER BY total DESC") + " LIMIT ?",
            [*params, top_n if not chrono else 400],
        )
        for r in rows:
            mcc_v = int(r["mcc"]) if r["mcc"] is not None else None
            groups.append({
                "key": str(r["k"]),
                "label": _label(group_by, str(r["k"]), {"mcc": mcc_v, "category": r["category"]}),
                "total": r2(r["total"]),
                "count": int(r["n"]),
                "share": round(float(r["total"]) / total, 4) if total else 0.0,
            })
    return {
        "filters": {"category": cats, "basket": bsk, "merchant": merchant, "mcc": mcc,
                    "group_by": group_by, "direction": direction},
        "total": r2(total),
        "count": count,
        "avg_tx": r2(total / count) if count else 0.0,
        "groups": groups,
        "period": {"start": s.isoformat(), "end": e.isoformat(),
                   "days": (e - s).days + 1},
    }


def search_transactions(customer_id: str, start: str | date | None = None,
                        end: str | date | None = None, category: str | list[str] | None = None,
                        basket: str | None = None, merchant: str | None = None,
                        min_amount: float | None = None, max_amount: float | None = None,
                        text: str | None = None, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List individual transactions (newest first) matching the filters.

    Default period is the whole history up to as-of. ``limit`` is capped at 200.
    """
    db.ensure_customer(customer_id)
    limit = max(1, min(int(limit or 50), 200))
    offset = max(0, int(offset or 0))
    s, e = _period(start, end, None)
    where, params = _build_where(customer_id, s, e, _norm_category(category), _norm_basket(basket),
                                 merchant, None, "all", min_amount, max_amount, text)
    total = int(db.scalar(f"SELECT count(*) FROM tx WHERE {where}", params) or 0)
    rows = db.query(f"{TX_SELECT} WHERE {where} ORDER BY tx_timestamp DESC LIMIT ? OFFSET ?",
                    [*params, limit, offset])
    return {"items": [tx_to_dict(r) for r in rows], "total_count": total,
            "limit": limit, "offset": offset}
