"""Safe-to-spend: "How much can I spend today without hurting future me?"

The single most useful number for day-to-day money decisions, and the one most banking
apps get wrong by showing the raw balance. Our formula is deliberately simple enough to
explain in one sentence on the home screen:

    safe_total = balance
               − upcoming bills before next payday        (recurring.upcoming_bills)
               − irregular-essentials buffer              (avg monthly irregular × days/30.4)
               − goal contributions                       (Σ goal.monthly_contribution × days/30.4)
    safe_per_day   = safe_total / days_until_payday
    safe_this_week = safe_per_day × min(7, days_until_payday)

* **Next payday** comes from salary history (median day-of-month, see
  :func:`app.analytics.common.detect_payday`). A late salary makes us plan until the end
  of the month instead of assuming money arrives tomorrow.
* **Saving transfers that are triggered by the salary** (e.g. a sweep the day after
  payday) are not counted while this month's salary is still missing; savings that are due
  from money already received *are* counted — paying future-you first is a bill too.
* **Status** compares ``safe_per_day`` with what this customer typically spends per day on
  flexible things (leaks + everyday groceries/transit): ``comfortable`` ≥ 90 % of typical,
  ``tight`` ≥ 40 %, otherwise ``critical``.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.i18n import day, eur, tr
from app.analytics.cache import ledger_cache
from app.analytics.common import (
    DAYS_PER_MONTH,
    as_of,
    basket_monthly_avg,
    current_balance,
    detect_payday,
    full_months_window,
    month_start,
    r2,
)
from app.analytics.recurring import recurring_payments, upcoming_bills


def _goal_monthly_total(customer_id: str) -> float:
    from app.analytics.goals import list_goals  # local import: goals imports this module's peers

    return sum(float(g.get("monthly_contribution") or 0.0) for g in list_goals(customer_id)
               if (g.get("progress") or 0) < 1)


@ledger_cache()
def typical_daily_flexible(customer_id: str, months: int = 3) -> float:
    """Average daily spend on flexible day-to-day items over the last complete months:
    the leak basket plus fixed spending that is *not* a bill (groceries, transit)."""
    start, end = full_months_window(months)
    v = db.scalar(
        "SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx WHERE customer_id = ? "
        "AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 AND ("
        " basket = 'leak' OR (basket = 'fixed' AND category NOT IN ('Housing','Utilities')"
        " AND NOT is_recurring))",
        [customer_id, start, end],
    )
    days = (end - start).days + 1
    return float(v or 0.0) / days


def compute(customer_id: str) -> dict[str, Any]:
    """Full computation, also returning intermediate values reused by other analytics."""
    db.ensure_customer(customer_id)
    today = as_of()
    pay = detect_payday(customer_id)
    nxt = pay["next_payday"]
    days = max((nxt - today).days, 1)
    balance = current_balance(customer_id)

    rec = recurring_payments(customer_id)
    bills = upcoming_bills(customer_id, nxt, items=rec["items"])
    salary_this_month = pay["last_payday"] is not None and pay["last_payday"] >= month_start(today)
    if not salary_this_month and pay["typical_day"] is not None:
        linked = []
        for b in bills:
            if b["basket"] != "saving":
                linked.append(b)
                continue
            due = b["expected_date"]
            same_month = due[:7] == today.strftime("%Y-%m")
            stream_day = next((i["day_of_month"] for i in rec["items"] if i["label"] == b["label"]), 0)
            salary_linked = 0 <= stream_day - pay["typical_day"] <= 7
            if not (same_month and salary_linked):
                linked.append(b)
        bills = linked
    bills_total = sum(b["amount"] for b in bills)

    avg = basket_monthly_avg(customer_id, 6)
    irregular_buffer = avg["irregular"] * days / DAYS_PER_MONTH
    goal_contrib = _goal_monthly_total(customer_id) * days / DAYS_PER_MONTH

    safe_total = max(0.0, balance - bills_total - irregular_buffer - goal_contrib)
    per_day = safe_total / days
    per_week = per_day * min(7, days)
    typical = typical_daily_flexible(customer_id)
    if safe_total <= 0 or per_day < 0.4 * typical:
        status = "critical"
    elif per_day < 0.9 * typical:
        status = "tight"
    else:
        status = "comfortable"

    late_note = tr(
        f" Your salary usually arrives around day {pay['typical_day']} but hasn't "
        f"landed yet this month, so we plan until {day(nxt)} to be safe.",
        f" Palkkasi tulee yleensä noin kuun {pay['typical_day']}. päivänä, mutta se ei ole vielä "
        f"tullut tässä kuussa, joten varmuuden vuoksi suunnittelemme {day(nxt)} asti.",
        f" Din lön brukar komma runt den {pay['typical_day']} i månaden men har inte kommit "
        f"ännu den här månaden, så för säkerhets skull planerar vi fram till {day(nxt)}.",
    ) if pay["late"] else ""
    explanation = tr(
        f"From your balance of {balance:.2f} € we set aside {bills_total:.2f} € for "
        f"{len(bills)} upcoming bill(s), {irregular_buffer:.2f} € as a buffer for irregular "
        f"essentials (health, repairs, car) and {goal_contrib:.2f} € for your goals. "
        f"That leaves {safe_total:.2f} € for the {days} day(s) until payday "
        f"({day(nxt)}): about {per_day:.2f} € a day. You usually spend about "
        f"{typical:.2f} € a day on flexible things.{late_note}",
        f"Saldostasi {eur(balance, 2)} varaamme {eur(bills_total, 2)} tuleviin laskuihin "
        f"({len(bills)} kpl), {eur(irregular_buffer, 2)} puskuriksi epäsäännöllisiin "
        f"välttämättömiin menoihin (terveys, korjaukset, auto) ja {eur(goal_contrib, 2)} tavoitteillesi. "
        f"Jäljelle jää {eur(safe_total, 2)} palkkapäivään ({day(nxt)}) asti, {days} päiväksi: "
        f"noin {eur(per_day, 2)} päivässä. Tavallisesti käytät joustaviin menoihin noin "
        f"{eur(typical, 2)} päivässä.{late_note}",
        f"Av ditt saldo på {eur(balance, 2)} lägger vi undan {eur(bills_total, 2)} för "
        f"{len(bills)} kommande räkning(ar), {eur(irregular_buffer, 2)} som buffert för oregelbundna "
        f"måsten (hälsa, reparationer, bil) och {eur(goal_contrib, 2)} för dina mål. "
        f"Kvar blir {eur(safe_total, 2)} för de {days} dagarna fram till lönedagen "
        f"({day(nxt)}): ungefär {eur(per_day, 2)} per dag. Vanligtvis lägger du ungefär "
        f"{eur(typical, 2)} per dag på flexibla utgifter.{late_note}",
    )
    return {
        "balance": r2(balance),
        "next_payday": nxt.isoformat(),
        "days_until_payday": days,
        "upcoming_bills": [{"label": b["label"], "amount": b["amount"],
                            "expected_date": b["expected_date"], "category": b["category"],
                            "basket": b["basket"]} for b in bills],
        "upcoming_bills_total": r2(bills_total),
        "irregular_buffer": r2(irregular_buffer),
        "goal_contributions": r2(goal_contrib),
        "safe_total": r2(safe_total),
        "safe_per_day": r2(per_day),
        "safe_this_week": r2(per_week),
        "typical_daily_spend": r2(typical),
        "status": status,
        "payday_detected_from": pay["source"],
        "payday_typical_day": pay["typical_day"],
        "salary_late": pay["late"],
        "explanation": explanation,
        "formula": tr(
            "safe_total = balance - upcoming bills - irregular buffer - goal contributions; "
            "per day = safe_total / days until payday",
            "turvallinen summa = saldo − tulevat laskut − epäsäännöllisten puskuri − tavoitesäästöt; "
            "per päivä = turvallinen summa / päivät palkkapäivään",
            "trygg summa = saldo − kommande räkningar − buffert för oregelbundna − sparande till mål; "
            "per dag = trygg summa / dagar till lönedagen",
        ),
    }


def safe_to_spend(customer_id: str) -> dict[str, Any]:
    """SPEC §3.1 ``safe_to_spend`` — see module docstring for the formula."""
    return compute(customer_id)


__all__ = ["safe_to_spend", "typical_daily_flexible"]
