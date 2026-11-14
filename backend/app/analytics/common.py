"""Shared helpers for the analytics package: dates, money, row shaping, base aggregates.

Why a common module
-------------------
Every analytic answers questions about *the same* customer ledger relative to *the same*
"today" (``AS_OF_DATE``). Keeping the calendar maths (full months, current month, payday
windows), the money rounding and the canonical ``Tx`` JSON shape in one place guarantees
that the home screen, the chat agent and the insights tab never disagree by a cent.

Conventions
-----------
* Money out is negative in the ledger; *reported* spending totals are positive numbers.
* "Monthly average" = mean over the last ``n`` **complete** calendar months before the
  as-of month (the running month is partial and would bias averages down).
* Every SQL statement is parameterised; nothing user-supplied is ever string-formatted.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.i18n import tr
from app.analytics.labels import icon_for, mcc_label, merchant_label

SPENDING_BASKETS: tuple[str, ...] = ("fixed", "irregular", "leak")
ALL_BASKETS: tuple[str, ...] = ("fixed", "irregular", "leak", "income", "saving")
DAYS_PER_MONTH = 30.44

BASKET_LABELS: dict[str, str] = {
    "fixed": "Fixed essentials",
    "irregular": "Irregular essentials",
    "leak": "Everyday leaks",
    "income": "Income",
    "saving": "Saving & investing",
}
BASKET_LABELS_L10N: dict[str, dict[str, str]] = {
    "en": BASKET_LABELS,
    "fi": {"fixed": "Kiinteät välttämättömät", "irregular": "Epäsäännölliset välttämättömät",
           "leak": "Arjen vuodot", "income": "Tulot", "saving": "Säästäminen ja sijoittaminen"},
    "sv": {"fixed": "Fasta måsten", "irregular": "Oregelbundna måsten", "leak": "Vardagsläckor",
           "income": "Inkomster", "saving": "Sparande och placeringar"},
}


def basket_label(basket: str) -> str:
    """Display name of a basket in the current request locale (:mod:`app.i18n`)."""
    from app.i18n import loc

    return BASKET_LABELS_L10N[loc()].get(basket, basket)


def r2(x: float | int | None) -> float:
    """Round money to cents (``None`` → 0.0). Avoids ``-0.0`` in JSON."""
    if x is None:
        return 0.0
    v = round(float(x), 2)
    return 0.0 if v == 0 else v


#: Dates the API accepts as input. Wider ranges only produce overflow errors downstream.
MIN_YEAR, MAX_YEAR = 2000, 2100


def parse_date(value: str | date | datetime | None) -> date | None:
    """Accept ISO strings (``2026-09-01`` or full timestamps), dates or datetimes."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()[:40]
    try:
        parsed = date.fromisoformat(s[:10])
    except ValueError as exc:
        raise ValueError(tr(f"Invalid date '{s}', expected YYYY-MM-DD",
                            f"Virheellinen päivämäärä '{s}', muodon on oltava VVVV-KK-PP",
                            f"Ogiltigt datum '{s}', formatet ska vara ÅÅÅÅ-MM-DD")) from exc
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:  # year 1 or 9999 would overflow date maths
        raise ValueError(tr(f"Date '{s}' is out of range ({MIN_YEAR}-{MAX_YEAR})",
                            f"Päivämäärä '{s}' on sallitun alueen ulkopuolella ({MIN_YEAR}–{MAX_YEAR})",
                            f"Datumet '{s}' ligger utanför det tillåtna intervallet ({MIN_YEAR}–{MAX_YEAR})"))
    return parsed


def as_of() -> date:
    return db.as_of()


def month_start(d: date) -> date:
    return d.replace(day=1)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, n: int) -> date:
    """Shift by ``n`` months, clamping the day (Jan 31 + 1 → Feb 28)."""
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def safe_day(year: int, month: int, day: int) -> date:
    return date(year, month, min(max(day, 1), calendar.monthrange(year, month)[1]))


def full_months_window(n: int = 6) -> tuple[date, date]:
    """(first day, last day) spanning the last ``n`` complete months before as-of month."""
    first_of_current = month_start(as_of())
    return add_months(first_of_current, -n), first_of_current - timedelta(days=1)


_MONTH_ABBR = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "fi": ("tammi", "helmi", "maalis", "huhti", "touko", "kesä", "heinä", "elo", "syys", "loka", "marras", "joulu"),
    "sv": ("jan", "feb", "mars", "apr", "maj", "juni", "juli", "aug", "sep", "okt", "nov", "dec"),
}


def month_label(ym: str) -> str:
    """``'2026-09'`` → ``'Sep 2026'`` / ``'syys 2026'`` / ``'sep 2026'`` (current locale)."""
    from app.i18n import loc

    y, m = ym.split("-")
    return f"{_MONTH_ABBR[loc()][int(m) - 1]} {y}"


def tx_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Canonical ``Tx`` JSON shape (SPEC §3.1) from a ``tx`` table row."""
    mcc = int(row["mcc_code"]) if row.get("mcc_code") is not None else None
    ts = row.get("tx_timestamp")
    return {
        "id": row["id"],
        "date": row["tx_date"].isoformat(),
        "timestamp": ts.isoformat() if ts is not None else None,
        "amount": r2(row["tx_amount_eur"]),
        "category": row["category"],
        "basket": row["basket"],
        "merchant_id": row.get("merchant_id"),
        "merchant_label": merchant_label(row.get("merchant_id"), mcc, row["category"]),
        "mcc": mcc,
        "mcc_label": mcc_label(mcc),
        "icon": icon_for(row["category"], mcc),
        "balance_after": r2(row["balance_after_eur"]),
        "type": row["transaction_type"],
    }


TX_SELECT = (
    "SELECT id, tx_date, tx_timestamp, tx_amount_eur, category, basket, merchant_id, mcc_code,"
    " balance_after_eur, transaction_type FROM tx"
)


@ledger_cache()
def current_balance(customer_id: str) -> float:
    """Balance after the last transaction on or before as-of."""
    v = db.scalar(
        "SELECT balance_after_eur FROM tx WHERE customer_id = ? "
        "ORDER BY tx_timestamp DESC LIMIT 1",
        [customer_id],
    )
    return r2(v)


@ledger_cache()
def basket_monthly_avg(customer_id: str, months: int = 6) -> dict[str, float]:
    """Average monthly total per basket over the last ``months`` complete months
    (positive numbers; income included)."""
    start, end = full_months_window(months)
    rows = db.query(
        "SELECT basket, sum(abs(tx_amount_eur)) AS total FROM tx "
        "WHERE customer_id = ? AND tx_date BETWEEN ? AND ? GROUP BY basket",
        [customer_id, start, end],
    )
    out = dict.fromkeys(ALL_BASKETS, 0.0)
    for r in rows:
        out[r["basket"]] = r2(r["total"] / months)
    return out


@ledger_cache()
def category_monthly_avg(customer_id: str, months: int = 6) -> list[dict[str, Any]]:
    """Average monthly spend per (category, basket) over complete months, biggest first."""
    start, end = full_months_window(months)
    rows = db.query(
        "SELECT category, basket, sum(-tx_amount_eur) AS total, count(*) AS n FROM tx "
        "WHERE customer_id = ? AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 "
        "AND basket IN ('fixed','irregular','leak') GROUP BY ALL ORDER BY total DESC",
        [customer_id, start, end],
    )
    return [
        {"category": r["category"], "basket": r["basket"], "monthly": r2(r["total"] / months),
         "count": int(r["n"])}
        for r in rows
    ]


@ledger_cache()
def monthly_flows(customer_id: str, months: int = 6) -> dict[str, float]:
    """Average monthly income / spending / saving / surplus over complete months.

    ``surplus`` = income − spending. Saving transfers are *not* subtracted: money the
    customer already moves to savings is part of what they can redirect to goals.
    """
    b = basket_monthly_avg(customer_id, months)
    spending = b["fixed"] + b["irregular"] + b["leak"]
    return {
        "income": r2(b["income"]),
        "spending": r2(spending),
        "saving": r2(b["saving"]),
        "surplus": r2(b["income"] - spending),
        "fixed": b["fixed"],
        "irregular": b["irregular"],
        "leak": b["leak"],
    }


@ledger_cache()
def detect_payday(customer_id: str) -> dict[str, Any]:
    """Estimate the next payday from salary history.

    Method: take Salary credits of the last ~7 months (fall back to any income if the
    customer has no salary). The *typical day* is the median day-of-month.
    * If this month's salary already arrived → next payday = typical day next month.
    * Else if the typical day is still ahead → this month's typical day.
    * Else the salary is late → plan conservatively until the end of the month
      (a budget that assumes money arrives tomorrow is the dangerous kind).
    Returns ``{"next_payday": date, "typical_day": int|None, "last_payday": date|None,
    "source": "salary|other_income|none", "late": bool}``.
    """
    today = as_of()
    since = add_months(month_start(today), -7)
    source = "salary"
    rows = db.query(
        "SELECT tx_date FROM tx WHERE customer_id = ? AND category = 'Salary' "
        "AND tx_date >= ? ORDER BY tx_date",
        [customer_id, since],
    )
    if not rows:
        source = "other_income"
        rows = db.query(
            "SELECT tx_date FROM tx WHERE customer_id = ? AND basket = 'income' "
            "AND tx_date >= ? ORDER BY tx_date",
            [customer_id, since],
        )
    if not rows:
        return {"next_payday": month_end(today) if month_end(today) > today
                else today + timedelta(days=30), "typical_day": None, "last_payday": None,
                "source": "none", "late": False}
    dates = [r["tx_date"] for r in rows]
    typical = int(round(median(d.day for d in dates)))
    last = dates[-1]
    late = False
    if last >= month_start(today):
        nxt = add_months(month_start(today), 1)
        nxt = safe_day(nxt.year, nxt.month, typical)
    else:
        candidate = safe_day(today.year, today.month, typical)
        if candidate > today:
            nxt = candidate
        else:
            late = True
            nxt = month_end(today) if month_end(today) > today else today + timedelta(days=1)
    return {"next_payday": nxt, "typical_day": typical, "last_payday": last,
            "source": source, "late": late}


def tx_count_and_period(customer_id: str, start: date | None = None,
                        end: date | None = None) -> dict[str, Any]:
    """Number of transactions an answer is based on (used for 'Based on N transactions')."""
    start = start or date(1900, 1, 1)
    end = end or as_of()
    n = db.scalar(
        "SELECT count(*) FROM tx WHERE customer_id = ? AND tx_date BETWEEN ? AND ?",
        [customer_id, start, end],
    )
    return {"tx_count": int(n or 0), "period": f"{start.isoformat()}..{end.isoformat()}"}
