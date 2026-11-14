"""Home-screen overview: everything the hero screen needs in one round-trip.

Why one endpoint
----------------
On a phone every request costs battery and latency. ``GET /overview`` bundles balance,
30-day trend, this month's money in/out by basket, safe-to-spend, goals, the 8 latest
transactions and nudges, so the S-mobiili home card can render in a single call
(~100 ms server side). Each part is also available as its own function/endpoint for the
agent and the insights tab. ``recovery`` is additive: the balance/cashflow diagnosis
(``balance_repair`` / ``cashflow_stabilizing`` / ``ordinary`` / ``unknown``) with the
safe-to-spend urgency kept as a separate field.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.analytics.common import (
    TX_SELECT,
    as_of,
    current_balance,
    month_start,
    r2,
    tx_to_dict,
)
from app.demo import DEMO_CUSTOMERS, display_name


@ledger_cache()
def get_balance(customer_id: str) -> dict[str, Any]:
    """Current balance and a daily end-of-day balance series for the last 30 days.

    Days without transactions carry the previous balance forward, so the sparkline is
    continuous (31 points: as_of-30 … as_of).
    """
    db.ensure_customer(customer_id)
    today = as_of()
    start = today - timedelta(days=30)
    rows = db.query(
        "SELECT tx_date, arg_max(balance_after_eur, tx_timestamp) AS bal FROM tx "
        "WHERE customer_id = ? AND tx_date BETWEEN ? AND ? GROUP BY tx_date ORDER BY tx_date",
        [customer_id, start, today],
    )
    opening = db.scalar(
        "SELECT balance_after_eur FROM tx WHERE customer_id = ? AND tx_date < ? "
        "ORDER BY tx_timestamp DESC LIMIT 1",
        [customer_id, start],
    )
    by_day = {r["tx_date"]: float(r["bal"]) for r in rows}
    running = float(opening) if opening is not None else (rows[0]["bal"] if rows else 0.0)
    trend = []
    d = start
    while d <= today:
        running = by_day.get(d, running)
        trend.append({"date": d.isoformat(), "balance": r2(running)})
        d += timedelta(days=1)
    return {"balance": current_balance(customer_id), "as_of": today.isoformat(), "trend_30d": trend}


def month_summary(customer_id: str) -> dict[str, Any]:
    """Month-to-date income, spending (by basket) and saving for the as-of month."""
    today = as_of()
    rows = db.query(
        "SELECT basket, sum(abs(tx_amount_eur)) AS total FROM tx "
        "WHERE customer_id = ? AND tx_date BETWEEN ? AND ? GROUP BY basket",
        [customer_id, month_start(today), today],
    )
    t = {r["basket"]: float(r["total"]) for r in rows}
    by_basket = {b: r2(t.get(b, 0.0)) for b in ("fixed", "irregular", "leak")}
    return {
        "month": today.strftime("%Y-%m"),
        "income": r2(t.get("income", 0.0)),
        "spent": r2(sum(by_basket.values())),
        "saved": r2(t.get("saving", 0.0)),
        "by_basket": by_basket,
    }


def recent_transactions(customer_id: str, n: int = 8) -> list[dict[str, Any]]:
    rows = db.query(f"{TX_SELECT} WHERE customer_id = ? ORDER BY tx_timestamp DESC LIMIT ?",
                    [customer_id, n])
    return [tx_to_dict(r) for r in rows]


def get_overview(customer_id: str) -> dict[str, Any]:
    """Everything for the home screen (SPEC §3.2 ``GET /customers/{id}/overview``)."""
    from app.analytics.goals import list_goals
    from app.analytics.nudges import nudges
    from app.analytics.recovery import recovery
    from app.analytics.safe_to_spend import safe_to_spend

    cust = db.get_customer(customer_id)
    bal = get_balance(customer_id)
    demo = DEMO_CUSTOMERS.get(customer_id, {})
    sts = safe_to_spend(customer_id)
    return {
        "customer": {
            "id": customer_id,
            "name": display_name(customer_id),
            "age": cust["age"],
            "postal_code": cust["postal_code"],
            "avatar_emoji": demo.get("avatar_emoji", "🙂"),
        },
        "as_of": bal["as_of"],
        "balance": bal["balance"],
        "trend_30d": bal["trend_30d"],
        "month": month_summary(customer_id),
        "safe_to_spend": sts,
        "recovery": recovery(customer_id, sts),
        "goals": list_goals(customer_id),
        "recent_transactions": recent_transactions(customer_id, 8),
        "nudges": nudges(customer_id),
    }
