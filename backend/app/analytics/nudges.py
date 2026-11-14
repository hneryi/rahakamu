"""Proactive nudges: short, persona-neutral observations the character can say unprompted.

Why
---
Most people never open a budgeting screen; a friendly one-liner from the character on
the home screen ("Eating out is running 35 % above your usual pace") meets them where
they are. Each nudge carries an ``action_prompt`` — tapping it opens the chat with that
question, so the nudge becomes a lesson grounded in the user's data.

Rules are deterministic and cheap (no LLM), evaluated in priority order, returning 3–6.

**Recovery state first** (``analytics/recovery.py``): when the balance is negative or the
six-month cashflow is negative, the situation is not "tight but fine" — the customer
needs a repair path, so those nudges replace the generic list with exactly one primary
message plus at most two supporting ones, ordered everyday essentials/bills → ongoing
deficit correction → zero balance / small buffer when affordable. No peer comparison,
archetype, investing encouragement or savings-streak pressure there. ``unknown`` data
gets a small neutral support instead of a false green "safe to spend" tip.

Otherwise the generic list:

1. **warn** safe-to-spend is ``tight``/``critical``.
2. **warn / celebrate** month-to-date leak spending vs. the usual pace (±20 %).
3. **goal** the active goal closest to completion: what is left and the monthly step.
4. **tip** biggest cuttable leak with the yearly saving of a realistic cut.
5. **tip** the next bill before payday.
6. **celebrate** savings rate ≥ 15 % over the last 6 months.
7. **tip** the spender archetype (fallback so there are always ≥ 3).

Text is neutral and in the request locale (en / fi / sv, :mod:`app.i18n`); the persona
layer (Sisu / Aava) restyles it in the chat. ``action_prompt`` is in the same language, so
tapping it starts the chat in the user's language.
"""

from __future__ import annotations

import calendar
from typing import Any

from app import db
from app.analytics.common import as_of, basket_monthly_avg, month_start, monthly_flows
from app.analytics.recovery import (
    STATE_BALANCE_REPAIR,
    STATE_CASHFLOW_STABILIZING,
    STATE_ORDINARY,
    STATE_UNKNOWN,
    recovery,
)
from app.i18n import day, eur, tr

MAX_NUDGES = 6


def nudges(customer_id: str) -> list[dict[str, Any]]:
    """3–6 rule-based nudges (see module docstring)."""
    from app.analytics.goals import leak_cut_candidates, list_goals
    from app.analytics.profile import spender_profile
    from app.analytics.safe_to_spend import safe_to_spend

    db.ensure_customer(customer_id)
    out: list[dict[str, Any]] = []
    today = as_of()

    sts = safe_to_spend(customer_id)
    rec = recovery(customer_id, sts)
    if rec["state"] in (STATE_BALANCE_REPAIR, STATE_CASHFLOW_STABILIZING):
        return _recovery_nudges(rec, sts)[:MAX_NUDGES]
    if rec["state"] == STATE_UNKNOWN:
        return _unknown_nudges()
    if sts["status"] in ("tight", "critical"):
        per_day, days, usual = eur(sts["safe_per_day"], 0), sts["days_until_payday"], eur(sts["typical_daily_spend"], 0)
        out.append({
            "id": "safe_to_spend_low", "kind": "warn", "emoji": "🧯" if sts["status"] == "critical" else "⚠️",
            "text": tr(f"Safe to spend is {per_day} a day until payday ({days} days). You usually spend {usual}.",
                       f"Turvallisesti käytettävissä on {per_day} päivässä palkkapäivään asti ({days} pv). "
                       f"Tavallisesti käytät {usual}.",
                       f"Tryggt att använda är {per_day} per dag fram till lönedagen ({days} dagar). "
                       f"Vanligtvis lägger du {usual}."),
            "action_prompt": tr("How do I make my money last until payday?",
                                "Miten saan rahani riittämään palkkapäivään asti?",
                                "Hur får jag pengarna att räcka till lönedagen?"),
        })

    avg = basket_monthly_avg(customer_id, 3)
    dim = calendar.monthrange(today.year, today.month)[1]
    mtd_leak = float(db.scalar(
        "SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx WHERE customer_id = ? AND basket = 'leak' "
        "AND tx_date BETWEEN ? AND ?", [customer_id, month_start(today), today]) or 0.0)
    expected = avg["leak"] * today.day / dim
    if expected > 20:
        ratio = mtd_leak / expected
        if ratio >= 1.2:
            pct, so_far = round((ratio - 1) * 100), eur(mtd_leak, 0)
            out.append({"id": "leak_pace_high", "kind": "warn", "emoji": "💸",
                        "text": tr(f"Everyday leaks are running {pct} % above your usual pace this month ({so_far} so far).",
                                   f"Arjen vuodot kulkevat tässä kuussa {pct} % tavallista nopeammin (tähän mennessä {so_far}).",
                                   f"Vardagsläckorna går {pct} % snabbare än vanligt den här månaden ({so_far} hittills)."),
                        "action_prompt": tr("Where is my money leaking this month?",
                                            "Mihin rahani vuotavat tässä kuussa?",
                                            "Var läcker mina pengar den här månaden?")})
        elif ratio <= 0.8:
            pct = round((1 - ratio) * 100)
            out.append({"id": "leak_pace_low", "kind": "celebrate", "emoji": "🎉",
                        "text": tr(f"Your everyday leaks are {pct} % below your usual pace this month. Keep the streak going!",
                                   f"Arjen vuotosi ovat tässä kuussa {pct} % tavallista pienemmät. Jatka samaan malliin!",
                                   f"Dina vardagsläckor ligger {pct} % under din vanliga takt den här månaden. Fortsätt så!"),
                        "action_prompt": tr("How much am I saving compared to a normal month?",
                                            "Paljonko säästän tavalliseen kuukauteen verrattuna?",
                                            "Hur mycket sparar jag jämfört med en vanlig månad?")})

    active = [g for g in list_goals(customer_id) if g["progress"] < 1]
    if active:
        g = max(active, key=lambda x: x["progress"])
        name, done, left = g["name"], f"{g['progress'] * 100:.0f} %", eur(g["remaining"], 0)
        monthly = eur(g["monthly_contribution"], 0) if g["monthly_contribution"] else ""
        # "keeps you on track" is only honest when the real surplus covers all active goals
        affordable = monthly_flows(customer_id, 6)["surplus"] >= sum(x["monthly_contribution"] for x in active)
        if not monthly:
            step = ""
        elif affordable:
            step = tr(f" {monthly}/month keeps you on track.", f" {monthly}/kk pitää sinut aikataulussa.",
                      f" {monthly}/mån. håller dig på rätt spår.")
        else:
            step = tr(f" It needs {monthly}/month, more than you currently have left over.",
                      f" Se vaatii {monthly}/kk, enemmän kuin sinulle tällä hetkellä jää yli.",
                      f" Det kräver {monthly}/mån., mer än du har över just nu.")
        out.append({"id": f"goal_{g['id']}", "kind": "goal", "emoji": g["emoji"],
                    "text": tr(f"{name}: {done} done, {left} to go.{step}",
                               f"{name}: {done} valmiina, {left} jäljellä.{step}",
                               f"{name}: {done} klart, {left} kvar.{step}"),
                    "action_prompt": tr(f"Help me reach my {name} goal faster",
                                        f"Auta minua saavuttamaan tavoite {name} nopeammin",
                                        f"Hjälp mig att nå målet {name} snabbare")})

    cuts = leak_cut_candidates(customer_id)
    if cuts:
        c = cuts[0]
        label, monthly, yearly, pct = c["label"], eur(c["current_monthly"], 0), eur(c["monthly_saving"] * 12, 0), c["cut_pct"]
        out.append({"id": f"cut_{c['category'].lower().replace(' ', '_')}", "kind": "tip", "emoji": "✂️",
                    "text": tr(f"{label} costs you about {monthly} a month. Cutting {pct} % would free ~{yearly} a year.",
                               f"{label} maksaa sinulle noin {monthly} kuukaudessa. {pct} % leikkaus vapauttaisi "
                               f"noin {yearly} vuodessa.",
                               f"{label} kostar dig ungefär {monthly} i månaden. Att skära ner med {pct} % skulle "
                               f"frigöra cirka {yearly} om året."),
                    "action_prompt": tr(f"How much could I save if I reduced {label.lower()} by {pct}%?",
                                        f"Paljonko säästäisin, jos leikkaisin {pct} % menoista ({label.lower()})?",
                                        f"Hur mycket skulle jag spara om jag minskade {label.lower()} med {pct} %?")})

    bills = [b for b in sts["upcoming_bills"] if b["basket"] != "saving"]
    if bills:
        b = bills[0]
        label, amount, when = b["label"].lower(), eur(b["amount"], 0), day(b["expected_date"])
        out.append({"id": "next_bill", "kind": "tip", "emoji": "📅",
                    "text": tr(f"Heads-up: {label} of about {amount} is due around {when}.",
                               f"Muistutus: {label}, noin {amount}, erääntyy noin {when}.",
                               f"Påminnelse: {label} på ungefär {amount} förfaller runt {when}."),
                    "action_prompt": tr("What bills are coming before my next payday?",
                                        "Mitä laskuja on tulossa ennen seuraavaa palkkapäivää?",
                                        "Vilka räkningar kommer före nästa lönedag?")})

    flows = monthly_flows(customer_id, 6)
    if flows["income"] > 0:
        rate = flows["surplus"] / flows["income"]
        if rate >= 0.15:
            kept = f"{rate * 100:.0f} %"
            out.append({"id": "savings_rate", "kind": "celebrate", "emoji": "💪",
                        "text": tr(f"You kept {kept} of your income over the last 6 months. Strong!",
                                   f"Sinulle jäi {kept} tuloistasi viimeisen 6 kuukauden aikana. Vahvaa!",
                                   f"Du behöll {kept} av din inkomst under de senaste 6 månaderna. Starkt!"),
                        "action_prompt": tr("How do I compare to people my age?",
                                            "Miten vertaudun ikätovereihini?",
                                            "Hur står jag mig jämfört med jämnåriga?")})

    if len(out) < 3 or len(out) < MAX_NUDGES:
        p = spender_profile(customer_id)
        arch = p["archetype"]["name"]
        out.append({"id": "archetype", "kind": "tip", "emoji": p["archetype"]["emoji"],
                    "text": tr(f"Your money style: {arch}. Curious what that means?",
                               f"Rahatyylisi: {arch}. Haluatko tietää, mitä se tarkoittaa?",
                               f"Din pengastil: {arch}. Nyfiken på vad det betyder?"),
                    "action_prompt": tr("What kind of spender am I?", "Millainen kuluttaja olen?",
                                        "Hurdan konsument är jag?")})
    if len(out) < 3:
        per_day = eur(sts["safe_per_day"], 0)
        out.append({"id": "safe_to_spend", "kind": "tip", "emoji": "🟢",
                    "text": tr(f"You can spend about {per_day} a day until payday.",
                               f"Voit käyttää noin {per_day} päivässä palkkapäivään asti.",
                               f"Du kan använda ungefär {per_day} per dag fram till lönedagen."),
                    "action_prompt": tr("What is safe for me to spend this week?",
                                        "Paljonko voin turvallisesti käyttää tällä viikolla?",
                                        "Hur mycket kan jag tryggt använda den här veckan?")})
    if len(out) < 3:
        out.append({"id": "learn", "kind": "tip", "emoji": "🧺",
                    "text": tr("Fixed, irregular, leaks: know your three money baskets.",
                               "Kiinteät, epäsäännölliset, vuodot: tunne kolme rahakoriasi.",
                               "Fasta, oregelbundna, läckor: lär känna dina tre pengakorgar."),
                    "action_prompt": tr("Explain the three money baskets", "Selitä kolme rahakoria",
                                        "Förklara de tre pengakorgarna")})
    return out[:MAX_NUDGES]


def _deficit_nudge(rec: dict[str, Any]) -> dict[str, Any]:
    deficit = eur(rec["deficit"])
    return {
        "id": "recovery_deficit", "kind": "warn", "emoji": "📉",
        "text": tr(f"Over the last six full months spending has averaged {deficit} more than income. Shall we look at where that difference comes from?",
                   f"Viimeisten kuuden täyden kuukauden aikana menoja on ollut keskimäärin {deficit} tuloja enemmän. Katsotaanko, mistä ero muodostuu?",
                   f"Under de sex senaste hela månaderna har utgifterna varit i genomsnitt {deficit} mer än inkomsten. Ska vi titta på var skillnaden kommer från?"),
        "action_prompt": tr("Where does the six-month spending gap come from?",
                            "Mistä kuuden kuukauden menoero muodostuu?",
                            "Var kommer utgiftsgapet på sex månader från?"),
    }


def _positive_cashflow_nudge(rec: dict[str, Any]) -> dict[str, Any]:
    surplus = eur(rec["monthly_surplus"])
    return {
        "id": "recovery_cashflow_positive", "kind": "tip", "emoji": "📈",
        "text": tr(f"The last six full months averaged a surplus of {surplus} a month. Let's check the current situation separately.",
                   f"Kuuden täyden kuukauden ylijäämä oli keskimäärin {surplus}/kk. Tarkistetaan nykytilanne erikseen.",
                   f"De senaste sex hela månaderna gav ett överskott på i genomsnitt {surplus}/mån. Vi kontrollerar nuläget separat."),
        "action_prompt": tr("Where does the six-month spending gap come from?",
                            "Mistä kuuden kuukauden menoero muodostuu?",
                            "Var kommer utgiftsgapet på sex månader från?"),
    }


def _bills_nudge(sts: dict[str, Any], bills: list[dict[str, Any]]) -> dict[str, Any]:
    total = eur(sum(b["amount"] for b in bills), 0)
    return {
        "id": "recovery_bills", "kind": "tip", "emoji": "📅",
        "text": tr(f"Bills of about {total} are due before payday. Let's check which are essential first.",
                   f"Ennen palkkapäivää erääntyy laskuja noin {total}. Tarkistetaan ensin, mitkä niistä ovat välttämättömiä.",
                   f"Räkningar på ungefär {total} förfaller före lönedagen. Vi kontrollerar först vilka som är nödvändiga."),
        "action_prompt": tr("How do I make it to payday — which bills come first?",
                            "Miten selviän palkkapäivään asti ja mitkä laskut tulevat ensin?",
                            "Hur klarar jag mig till lönedagen och vilka räkningar kommer först?"),
    }


def _buffer_nudge() -> dict[str, Any]:
    return {
        "id": "recovery_buffer", "kind": "tip", "emoji": "🛟",
        "text": tr("When affordable, a small buffer can help with unexpected expenses.",
                   "Kun rahaa jää yli, pieni puskuri voi auttaa yllättävissä menoissa.",
                   "När det finns utrymme kan en liten buffert hjälpa med oväntade utgifter."),
        "action_prompt": tr("What is an emergency buffer and how do I start one?",
                            "Mikä on puskurirahasto ja miten aloitan sen?",
                            "Vad är en buffert och hur börjar jag en?"),
    }


def _essentials_nudge() -> dict[str, Any]:
    return {
        "id": "recovery_essentials", "kind": "tip", "emoji": "🧾",
        "text": tr("Start with essentials: food, housing, medicines, transport. Leaks can wait.",
                   "Aloitetaan välttämättömistä menoista: ruoka, asuminen, lääkkeet, liikkuminen. Vuodot odottavat.",
                   "Börja med det nödvändiga: mat, boende, medicin, transport. Läckorna kan vänta."),
        "action_prompt": tr("How do I make my money last until payday?",
                            "Miten saan rahani riittämään palkkapäivään asti?",
                            "Hur får jag pengarna att räcka till lönedagen?"),
    }


def _recovery_nudges(rec: dict[str, Any], sts: dict[str, Any]) -> list[dict[str, Any]]:
    """One primary + at most two supporting messages, essentials first."""
    balance = eur(abs(rec["balance"]), 2)
    deficit = eur(rec["deficit"], 0)
    surplus = rec["monthly_surplus"]

    if rec["state"] == STATE_BALANCE_REPAIR:
        primary = {
            "id": "recovery_balance", "kind": "warn", "emoji": "🔴",
            "text": tr(f"Your account is {balance} below zero. We start with everyday essentials and bills, not a savings challenge.",
                       f"Tilisi on {balance} miinuksella. Aloitetaan arjen välttämättömistä menoista ja laskuista, ei säästöhaasteesta.",
                       f"Kontot är {balance} under noll. Vi börjar med vardagens nödvändiga utgifter och räkningar, inte med en sparutmaning."),
            "action_prompt": tr("How do I get back to a positive balance?",
                                "Miten pääsen takaisin plussalle?",
                                "Hur kommer jag tillbaka till plus?"),
        }
    else:
        primary = {
            "id": "recovery_cashflow", "kind": "warn", "emoji": "📉",
            "text": tr(f"Your balance is at or above zero ({balance}), but spending has averaged {deficit} more than income over the last six full months — the buffer is shrinking.",
                       f"Saldo on vähintään nollassa ({balance}), mutta kuuden täyden kuukauden menoja on ollut keskimäärin {deficit} tuloja enemmän — puskuri hupenee.",
                       f"Saldot är noll eller högre ({balance}), men utgifterna har varit i genomsnitt {deficit} mer än inkomsten under de sex senaste hela månaderna — bufferten krymper."),
            "action_prompt": tr("How do I stop my buffer from shrinking?",
                                "Miten estän puskurin hupenemisen?",
                                "Hur hindrar jag att bufferten krymper?"),
        }

    supporting: list[dict[str, Any]] = []
    bills = [b for b in sts["upcoming_bills"] if b["basket"] != "saving"]
    if bills:
        supporting.append(_bills_nudge(sts, bills))
    supporting.append(_deficit_nudge(rec) if surplus < 0 else _positive_cashflow_nudge(rec))
    if surplus >= 0:
        supporting.append(_buffer_nudge())

    out = [primary, *supporting[:2]]
    if len(out) < 3:
        out.append(_essentials_nudge())
    return out


def _unknown_nudges() -> list[dict[str, Any]]:
    """Neutral support when the numbers are missing — never a false green status."""
    return [
        {
            "id": "recovery_unknown", "kind": "tip", "emoji": "❔",
            "text": tr("I do not have enough information, so I will not guess whether you are in the black.",
                       "Tietoja ei ole riittävästi, joten en arvaa, oletko plussalla vai et.",
                       "Jag har inte tillräckligt med information, så jag gissar inte om du är på plus."),
            "action_prompt": tr("What is my current money situation?", "Mikä on rahatilanteeni nyt?",
                                "Hur ser min pengasituation ut?"),
        },
        {
            "id": "learn", "kind": "tip", "emoji": "🧺",
            "text": tr("Fixed, irregular, leaks: know your three money baskets.",
                       "Kiinteät, epäsäännölliset, vuodot: tunne kolme rahakoriasi.",
                       "Fasta, oregelbundna, läckor: lär känna dina tre pengakorgar."),
            "action_prompt": tr("Explain the three money baskets", "Selitä kolme rahakoria",
                                "Förklara de tre pengakorgarna"),
        },
    ]
