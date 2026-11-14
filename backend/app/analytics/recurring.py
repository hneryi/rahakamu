"""Recurring payments ("bills & subscriptions") and upcoming-bill forecasting.

Why
---
Knowing what is *already committed* is the first step of any budget: safe-to-spend and
the survival planner subtract upcoming bills before telling anyone what is free to spend.

Detection method (transparent, no ML needed)
--------------------------------------------
Two kinds of *streams* are evaluated over the last 6 complete months:

1. **Bill categories without a merchant id** (Housing, Utilities, Invest Deposit,
   Salary Sweep): a stream is *monthly* when it appears in ≥ 4 of the 6 months. Utilities
   arrive as several small payments a month, so the stream amount is the average
   **monthly total** and ``payments_per_month`` tells the UI how many to expect.
2. **Merchant streams**: the same merchant paid at a roughly fixed rhythm with a stable
   amount (coefficient of variation < 0.25): monthly when the median gap between payments
   is 25–35 days, weekly when it is 6–8 days. Monthly merchant streams are exactly the
   ``is_recurring`` flag that moves a transaction into the *fixed* basket (see
   :mod:`app.db`), so the list and the basket meter always agree.

``upcoming_bills`` then projects each stream forward: for the running month it subtracts
what has already been paid (so a half-paid utility month only shows the remainder).
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median, pstdev
from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.analytics.common import (
    add_months,
    as_of,
    full_months_window,
    month_start,
    r2,
    safe_day,
)
from app.analytics.labels import category_default_label, merchant_label
from app.i18n import tr

BILL_CATEGORIES: tuple[str, ...] = ("Housing", "Utilities", "Invest Deposit", "Salary Sweep")
WINDOW_MONTHS = 6


def _category_streams(customer_id: str, start: date, end: date) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT category, basket, tx_date, -tx_amount_eur AS amt FROM tx "
        "WHERE customer_id = ? AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 "
        "AND merchant_id IS NULL AND category IN (?, ?, ?, ?) ORDER BY tx_date",
        [customer_id, start, end, *BILL_CATEGORIES],
    )
    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    items: list[dict[str, Any]] = []
    # The running month is partial: averaging it in would understate the stream (and make
    # "months seen" 7 of "the last 6"), so statistics use complete months only.
    current = as_of().strftime("%Y-%m")
    for cat, txs in by_cat.items():
        per_month: dict[str, float] = {}
        full_payments = 0
        for t in txs:
            ym = t["tx_date"].strftime("%Y-%m")
            if ym == current:
                continue
            per_month[ym] = per_month.get(ym, 0.0) + float(t["amt"])
            full_payments += 1
        if len(per_month) < 4:
            continue
        totals = list(per_month.values())
        avg = sum(totals) / len(totals)
        cv = pstdev(totals) / avg if avg else 0.0
        items.append({
            "label": category_default_label(cat) if cat != "Utilities" else tr("Utility bills", "Asumisen laskut", "Boenderäkningar"),
            "category": cat,
            "merchant_id": None,
            "avg_amount": r2(avg),
            "cadence": "monthly",
            "day_of_month": int(round(median(t["tx_date"].day for t in txs))),
            "last_date": txs[-1]["tx_date"].isoformat(),
            "basket": txs[-1]["basket"],
            "payments_per_month": round(full_payments / len(per_month), 1),
            "months_seen": len(per_month),
            "amount_cv": round(cv, 3),
            "stream": f"category:{cat}",
        })
    return items


def _merchant_streams(customer_id: str, start: date, end: date) -> list[dict[str, Any]]:
    rows = db.query(
        "SELECT merchant_id, mcc_code, category, basket, tx_date, -tx_amount_eur AS amt, "
        "is_recurring FROM tx WHERE customer_id = ? AND tx_date BETWEEN ? AND ? "
        "AND tx_amount_eur < 0 AND merchant_id IS NOT NULL ORDER BY merchant_id, tx_date",
        [customer_id, start, end],
    )
    by_m: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_m.setdefault(r["merchant_id"], []).append(r)
    items: list[dict[str, Any]] = []
    for mid, txs in by_m.items():
        if len(txs) < 4:
            continue
        amts = [float(t["amt"]) for t in txs]
        avg = sum(amts) / len(amts)
        cv = pstdev(amts) / avg if avg else 1.0
        gaps = [(b["tx_date"] - a["tx_date"]).days for a, b in zip(txs, txs[1:], strict=False)]
        med_gap = median(gaps) if gaps else 0
        cadence = None
        if 25 <= med_gap <= 35 and cv < 0.25:
            cadence = "monthly"
        elif 6 <= med_gap <= 8 and cv < 0.25 and len(txs) >= 8:
            cadence = "weekly"
        if cadence is None and not txs[-1]["is_recurring"]:
            continue
        cadence = cadence or "monthly"
        mcc = int(txs[-1]["mcc_code"]) if txs[-1]["mcc_code"] is not None else None
        items.append({
            "label": merchant_label(mid, mcc, txs[-1]["category"]),
            "category": txs[-1]["category"],
            "merchant_id": mid,
            "avg_amount": r2(avg),
            "cadence": cadence,
            "day_of_month": int(round(median(t["tx_date"].day for t in txs))),
            "last_date": txs[-1]["tx_date"].isoformat(),
            "basket": "fixed" if cadence == "monthly" else txs[-1]["basket"],
            "payments_per_month": 1.0 if cadence == "monthly" else 4.3,
            "months_seen": min(WINDOW_MONTHS, len({t["tx_date"].strftime("%Y-%m") for t in txs})),
            "amount_cv": round(cv, 3),
            "stream": f"merchant:{mid}",
        })
    return items


@ledger_cache()
def recurring_payments(customer_id: str) -> dict[str, Any]:
    """Detected recurring payments (bills, standing savings transfers, subscriptions).

    ``monthly_total`` sums the *spending* streams (fixed bills & subscriptions) as a monthly
    equivalent; ``monthly_saving_total`` sums automated saving transfers separately.
    """
    db.ensure_customer(customer_id)
    start, _ = full_months_window(WINDOW_MONTHS)
    end = as_of()
    items = _category_streams(customer_id, start, end) + _merchant_streams(customer_id, start, end)
    items.sort(key=lambda i: -i["avg_amount"])

    def monthly_equiv(i: dict[str, Any]) -> float:
        return i["avg_amount"] * (4.33 if i["cadence"] == "weekly" else 1.0)

    spend = [i for i in items if i["basket"] != "saving"]
    save = [i for i in items if i["basket"] == "saving"]
    return {
        "items": items,
        "monthly_total": r2(sum(monthly_equiv(i) for i in spend)),
        "monthly_saving_total": r2(sum(monthly_equiv(i) for i in save)),
        "method": tr("Bills = categories seen in at least 4 of the last 6 months; subscriptions = "
                     "same merchant at a ~monthly or weekly rhythm with a stable amount (CV < 0.25).",
                     "Laskut = kategoriat, joita on ollut vähintään 4 kuukautena viimeisten 6 kuukauden aikana; "
                     "tilaukset = sama kauppias noin kuukauden tai viikon välein vakaalla summalla (CV < 0,25).",
                     "Räkningar = kategorier som förekommit minst 4 av de senaste 6 månaderna; prenumerationer = "
                     "samma handlare ungefär varje månad eller vecka med ett stabilt belopp (CV < 0,25)."),
    }


def _paid_in_stream(customer_id: str, item: dict[str, Any], start: date, end: date) -> float:
    if item["merchant_id"]:
        v = db.scalar(
            "SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx WHERE customer_id = ? "
            "AND merchant_id = ? AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0",
            [customer_id, item["merchant_id"], start, end],
        )
    else:
        v = db.scalar(
            "SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx WHERE customer_id = ? "
            "AND category = ? AND merchant_id IS NULL AND tx_date BETWEEN ? AND ? "
            "AND tx_amount_eur < 0",
            [customer_id, item["category"], start, end],
        )
    return float(v or 0.0)


def upcoming_bills(customer_id: str, until: date, include_saving: bool = True,
                   items: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Project recurring streams into ``(as_of, until]``.

    Returns ``[{"label","amount","expected_date","category","basket","cadence"}]`` sorted by
    date. Running-month amounts are reduced by what was already paid this month.
    """
    today = as_of()
    if until <= today:
        return []
    if items is None:
        items = recurring_payments(customer_id)["items"]
    out: list[dict[str, Any]] = []
    for it in items:
        if not include_saving and it["basket"] == "saving":
            continue
        if it["cadence"] == "weekly":
            nxt = date.fromisoformat(it["last_date"]) + timedelta(days=7)
            while nxt <= until:
                if nxt > today:
                    out.append(_bill(it, it["avg_amount"], nxt))
                nxt += timedelta(days=7)
            continue
        m = month_start(today)
        while m <= until:
            due = safe_day(m.year, m.month, it["day_of_month"])
            amount = it["avg_amount"]
            if m == month_start(today):
                paid = _paid_in_stream(customer_id, it, m, today)
                amount = it["avg_amount"] - paid
                if amount < 0.25 * it["avg_amount"]:
                    m = add_months(m, 1)
                    continue
                if due <= today:  # partly paid multi-payment stream or late bill
                    due = today + timedelta(days=1)
            if today < due <= until:
                out.append(_bill(it, amount, due))
            m = add_months(m, 1)
    out.sort(key=lambda b: b["expected_date"])
    return out


def _bill(it: dict[str, Any], amount: float, due: date) -> dict[str, Any]:
    return {
        "label": it["label"],
        "amount": r2(amount),
        "expected_date": due.isoformat(),
        "category": it["category"],
        "basket": it["basket"],
        "cadence": it["cadence"],
    }
