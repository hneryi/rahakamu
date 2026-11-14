"""Survival planner: "How do I survive this month with 300 €?"

Why
---
When money is tight, people need a *concrete daily plan*, not a lecture. Given an amount
(default: current balance) and a date (default: next payday) this module subtracts the bills
that will hit before then, and splits what is left into per-category budgets that protect
essentials first.

Method
------
1. ``bills`` = recurring *spending* bills due in ``(as_of, until]``. Automated saving
   transfers are **paused** in survival mode (and a tip says so).
2. ``free_money``:
   * no ``amount`` given → the plan starts from the current balance, so
     ``free_money = balance − bills`` (``amount_mode = "balance_minus_bills"``);
   * an explicit ``amount`` ("How do I survive this month with 300 €?") is read the way
     people mean it — money to *live on* — so bills are listed and reminded about but not
     subtracted (``amount_mode = "living_money"``).
3. Typical daily spend per flexible category from the last 3 complete months (bills and
   detected subscriptions excluded) × days = what you would *normally* spend.
4. Allocation: if free money covers normal spending → ``ok``. Otherwise essentials
   (groceries, transport, health) get a lean 85 % of normal first and the rest is shared
   across leak categories pro rata → ``tight``. If even lean essentials don't fit →
   ``short`` and ``shortfall`` tells exactly how much is missing.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.analytics.common import as_of, current_balance, detect_payday, full_months_window, parse_date, r2
from app.analytics.labels import category_label_l10n
from app.analytics.recurring import upcoming_bills
from app.i18n import day, eur, tr

ESSENTIAL = ("Groceries", "Transportation", "Health")
FLEXIBLE = ("Groceries", "Transportation", "Health", "Restaurants", "Entertainment", "Lifestyle",
            "Home & Tech", "Travel")
LEAN_FACTOR = 0.85


@ledger_cache()
def _typical_daily(customer_id: str, months: int = 3) -> dict[str, float]:
    start, end = full_months_window(months)
    days = (end - start).days + 1
    rows = db.query(
        "SELECT category, sum(-tx_amount_eur) AS total FROM tx WHERE customer_id = ? "
        "AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 AND NOT is_recurring "
        "AND basket IN ('fixed','irregular','leak') AND category NOT IN ('Housing','Utilities') "
        "GROUP BY category",
        [customer_id, start, end],
    )
    return {r["category"]: float(r["total"]) / days for r in rows if r["category"] in FLEXIBLE}


def survival_plan(customer_id: str, amount: float | None = None,
                  until: str | date | None = None) -> dict[str, Any]:
    """Daily survival budget until ``until`` (see module docstring)."""
    db.ensure_customer(customer_id)
    today = as_of()
    amt = float(amount) if amount is not None else current_balance(customer_id)
    end = parse_date(until) or detect_payday(customer_id)["next_payday"]
    if end <= today:
        raise ValueError("until must be after the as-of date")
    days = (end - today).days

    all_bills = upcoming_bills(customer_id, end)
    bills = [b for b in all_bills if b["basket"] != "saving"]
    paused = [b for b in all_bills if b["basket"] == "saving"]
    bills_total = sum(b["amount"] for b in bills)
    amount_mode = "living_money" if amount is not None else "balance_minus_bills"
    free = amt if amount_mode == "living_money" else amt - bills_total

    daily = _typical_daily(customer_id)
    typical = {c: daily.get(c, 0.0) * days for c in FLEXIBLE if daily.get(c, 0.0) > 0}
    typical_total = sum(typical.values())
    ess_typical = {c: v for c, v in typical.items() if c in ESSENTIAL}
    leak_typical = {c: v for c, v in typical.items() if c not in ESSENTIAL}
    ess_lean = sum(ess_typical.values()) * LEAN_FACTOR
    budgets: dict[str, float] = {}
    shortfall = 0.0
    if free >= typical_total:
        risk = "ok"
        budgets = dict(typical)
        spare = free - typical_total
    elif free >= ess_lean:
        risk = "tight"
        room = free - ess_lean
        ess_extra_need = sum(ess_typical.values()) - ess_lean
        ess_extra = min(room, ess_extra_need)
        for c, v in ess_typical.items():
            share = v / sum(ess_typical.values()) if ess_typical else 0
            budgets[c] = v * LEAN_FACTOR + ess_extra * share
        room -= ess_extra
        leak_sum = sum(leak_typical.values())
        for c, v in leak_typical.items():
            budgets[c] = room * v / leak_sum if leak_sum else 0.0
        spare = 0.0
    else:
        risk = "short"
        avail = max(0.0, free)
        ess_sum = sum(ess_typical.values())
        for c, v in ess_typical.items():
            budgets[c] = avail * v / ess_sum if ess_sum else 0.0
        for c in leak_typical:
            budgets[c] = 0.0
        shortfall = ess_lean - free  # signed: money already missing after bills counts too
        spare = 0.0

    per_day = max(free, 0.0) / days
    tips: list[str] = []
    if risk != "ok" and leak_typical:
        top = max(leak_typical.items(), key=lambda kv: kv[1])
        what, normal, budget = category_label_l10n(top[0]).lower(), eur(top[1], 0), eur(budgets.get(top[0], 0), 0)
        tips.append(tr(f"Biggest flexible cost: {what} (normally {normal} in this period). Your budget is {budget}.",
                       f"Suurin joustava kulu: {what} (yleensä {normal} tällä jaksolla). Budjettisi on {budget}.",
                       f"Största flexibla kostnaden: {what} (normalt {normal} under perioden). Din budget är {budget}."))
    if "Groceries" in budgets:
        weeks = max(days / 7, 1)
        week = eur(budgets["Groceries"] / weeks, 0)
        tips.append(tr(f"Plan meals for the week: about {week} per week for groceries; cook in batches and "
                       "use what is already at home.",
                       f"Suunnittele viikon ateriat: ruokaostoksiin noin {week} viikossa; kokkaa isompia "
                       "eriä ja käytä se, mitä kotoa jo löytyy.",
                       f"Planera veckans måltider: ungefär {week} i veckan för mat; laga större satser och "
                       "använd det som redan finns hemma."))
    if paused and risk != "ok":
        what = ", ".join(sorted({b["label"].lower() for b in paused}))
        total = eur(sum(b["amount"] for b in paused), 0)
        tips.append(tr(f"Consider pausing {what} ({total}) until payday — restart it after.",
                       f"Harkitse tauon pitämistä: {what} ({total}) palkkapäivään asti — jatka sen jälkeen.",
                       f"Fundera på att pausa {what} ({total}) fram till lönedagen — starta igen efteråt."))
    if bills:
        b0 = bills[0]
        nxt, amt0, when, total = b0["label"].lower(), eur(b0["amount"], 0), day(b0["expected_date"]), eur(bills_total, 0)
        if amount_mode == "living_money":
            tips.append(tr(f"Bills of {total} are due before {day(end)} (next: {nxt} {amt0} around {when}); "
                           "keep that money separate from these budgets.",
                           f"Laskuja erääntyy {total} ennen {day(end)} (seuraavaksi: {nxt} {amt0} noin {when}); "
                           "pidä tämä raha erillään näistä budjeteista.",
                           f"Räkningar på {total} förfaller före {day(end)} (nästa: {nxt} {amt0} runt {when}); "
                           "håll de pengarna åtskilda från de här budgetarna."))
        else:
            tips.append(tr(f"Next bill: {nxt} {amt0} around {when}. Keep that money untouched.",
                           f"Seuraava lasku: {nxt} {amt0} noin {when}. Älä koske siihen rahaan.",
                           f"Nästa räkning: {nxt} {amt0} runt {when}. Låt de pengarna vara orörda."))
    if risk == "short":
        short = eur(shortfall, 0)
        if free < 0:  # already in the red after bills: say so instead of only the essentials gap
            behind, lean = eur(-free, 0), eur(ess_lean, 0)
            lead = tr(f"You are already about {behind} behind after bills, and lean essentials need another {lean}.",
                      f"Olet laskujen jälkeen jo noin {behind} miinuksella, ja niukat välttämättömät menot "
                      f"vaativat vielä {lean}.",
                      f"Efter räkningarna ligger du redan ungefär {behind} back, och de mest nödvändiga "
                      f"utgifterna kräver ytterligare {lean}.")
        else:
            lead = tr(f"You are about {short} short for lean essentials.",
                      f"Niukkoihin välttämättömiin menoihin puuttuu noin {short}.",
                      f"Det fattas ungefär {short} för de mest nödvändiga utgifterna.")
        tips.append(lead + tr(" Contact the biller early to agree a later due date, and ask S-Bank about "
                              "options before it is overdue.",
                              " Ota laskuttajaan yhteyttä ajoissa ja sovi myöhemmästä eräpäivästä, ja kysy "
                              "S-Pankista vaihtoehtoja ennen kuin lasku myöhästyy.",
                              " Kontakta fakturans avsändare i god tid och kom överens om en senare "
                              "förfallodag, och fråga S-Banken om alternativ innan räkningen blir försenad."))
    if risk == "ok":
        spare_txt = eur(spare, 0)
        tips.append(tr(f"You're covered with about {spare_txt} to spare: move it to your emergency fund on payday.",
                       f"Rahat riittävät, ja ylimääräistä jää noin {spare_txt}: siirrä se puskuriin palkkapäivänä.",
                       f"Pengarna räcker och det blir ungefär {spare_txt} över: flytta dem till din buffert på lönedagen."))
    cats = sorted(typical.keys(), key=lambda c: (c not in ESSENTIAL, -typical[c]))
    return {
        "amount": r2(amt),
        "until": end.isoformat(),
        "days": days,
        "upcoming_bills_total": r2(bills_total),
        "bills": bills,
        "paused_savings": paused,
        "amount_mode": amount_mode,
        "free_money": r2(free),
        "per_day": r2(per_day),
        "per_week": r2(per_day * 7),
        "category_budgets": [{"category": c, "label": category_label_l10n(c), "budget": r2(budgets.get(c, 0.0)),
                              "typical": r2(typical[c]), "essential": c in ESSENTIAL}
                             for c in cats],
        "risk": risk,
        "shortfall": r2(max(shortfall, 0.0)),
        "tips": tips[:5],
    }
