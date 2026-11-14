"""Offline intent router + persona-styled templated answers.

Why this exists
---------------
A demo (or a bank feature) cannot go blank because an inference endpoint is down. When
every LLM provider fails — or ``LLM_OFFLINE=1`` is set — this module answers with the
*same* tools and the *same* widgets as the LLM path, so the app looks and behaves almost
identically. It is also the safety net the orchestrator uses when the model returns an
empty answer after tool calls (:func:`compose_answer`).

How it works
------------
1. :func:`route` turns the latest user message into an :class:`Intent`: an ordered list
   of ``(tool, args)`` calls. Keyword patterns cover English, Finnish (including
   inflected stems like *taksi-*, *säästä-*, *selvi-*) and Swedish (*spara till*,
   *klarar jag*, *läcker*), amounts ("12000", "12 000 €", "12k", "300 euroa", "300 euro";
   "12 000 kr" is *not* euros and is ignored), percentages ("20 %", "20 prosenttia",
   "20 procent"), periods ("last month", "viime kuussa", "förra månaden", "in August",
   "elokuussa", "i augusti") and deadlines ("by June", "kesäkuuhun mennessä",
   "senast i juni", "in 18 months", "om 18 månader", "2027-06").
2. Each call runs through :func:`app.agent.tools.execute_tool` (so widgets, sources and
   consent rules are identical to the LLM path).
3. :func:`compose_answer` renders a short answer from the tool results using per-tool
   templates in the user's language, wrapped in the persona's voice: Sisu closes with a
   challenge, Aava with a reflective question, plus an occasional "💡" concept line.
   Every number in a template comes straight from a tool result.
"""

from __future__ import annotations

import asyncio
import random
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from app.agent import events as ev
from app.agent.events import ChatRequest, SSEEvent
from app.agent.followups import derive_mood, merge_sources, suggest_followups
from app.agent.lang import norm_locale, pick
from app.agent.personas import Persona, get_persona
from app.agent.tools import ToolContext, ToolResult, execute_tool, guess_goal_kind, status_label
from app.agent.vocab import (
    ARCHETYPE_L10N,
    BASKET_LABEL,
    MONTHS_FULL_EN,
    SUBCATEGORIES,
    add_months,
    category_label,
    fi_cost_stem,
    fi_inessive_period,
    fmt_eur,
    match_vocabulary,
    parse_iso,
)

# =============================================================================== parsing

_SV_MONTHS = ("januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december")
_FI_MONTHS = ("tammikuu", "helmikuu", "maaliskuu", "huhtikuu", "toukokuu", "kesäkuu", "heinäkuu", "elokuu", "syyskuu", "lokakuu", "marraskuu", "joulukuu")
_EN_MONTHS = tuple(m.lower() for m in MONTHS_FULL_EN)
_EN_MONTH_ABBR = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

_AMOUNT_RE = re.compile(
    r"(?<![\w.,/-])"
    r"(\d{1,3}(?:[  ]\d{3})+|\d{1,3}(?:,\d{3})+(?!\d)|\d+)"  # integer part with optional thousands separators
    r"(?:[.,](\d{1,2}))?(?![\d-])"  # optional decimals
    r"\s*(k\b|t\b|tuhatta\b|thousand\b|tusen\b)?"  # thousands multiplier
    r"\s*(%|prosent\w*|procent\w*|percent|pct)?"  # percentage (excluded from amounts)
    r"\s*(€|eur\b|euro\w*|e\b|kr\b|kronor\b|sek\b)?",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|prosent\w*|procent\w*|percent|pct)", re.IGNORECASE)
_ISO_RE = re.compile(r"\b(20\d{2})-(0[1-9]|1[0-2])(?:-(\d{2}))?\b")


def parse_amounts(text: str) -> list[float]:
    """Money amounts mentioned in ``text`` (percentages and bare years excluded)."""
    out: list[float] = []
    clean = _ISO_RE.sub(" ", text)
    for m in _AMOUNT_RE.finditer(clean):
        integer, decimals, mult, pct, cur = m.groups()
        if pct:
            continue
        if cur and cur.lower() in ("kr", "kronor", "sek"):
            continue  # not euros: the app only speaks euros, so never guess a conversion
        value = float(re.sub(r"[  ,]", "", integer) + (f".{decimals}" if decimals else ""))
        if mult:
            value *= 1000
        if not cur and not mult and 2024 <= value <= 2040 and not decimals:
            continue  # a year, not money
        if not cur and not mult and value < 10 and not decimals:
            continue  # "3 months", "6 more" – not money
        out.append(value)
    return out


def parse_percent(text: str) -> float | None:
    m = _PERCENT_RE.search(text)
    return float(m.group(1).replace(",", ".")) if m else None


def _month_index(text: str) -> tuple[int, int | None] | None:
    """Find a month name (en/fi/sv, inflected) and an optional 4-digit year after it."""
    low = text.lower()
    for i, stem in enumerate(_FI_MONTHS):
        m = re.search(stem + r"\w*(?:\s+(20\d{2}))?", low)
        if m:
            return i + 1, int(m.group(1)) if m.group(1) else None
    for i, name in enumerate(_SV_MONTHS):
        m = re.search(r"\b" + name + r"\b(?:\s+(20\d{2}))?", low)
        if m and not (name == "mars" and re.search(r"\bmars(?:ch| bar)\b", low)):
            return i + 1, int(m.group(1)) if m.group(1) else None
    for i, name in enumerate(_EN_MONTHS):
        m = re.search(r"\b(?:" + name + "|" + _EN_MONTH_ABBR[i] + r")\b\.?(?:\s+(20\d{2}))?", low)
        if m and not (name == "may" and re.search(r"\bmay i\b|\bi may\b", low)):
            return i + 1, int(m.group(1)) if m.group(1) else None
    return None


def _end_of_month(y: int, m: int) -> date:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return nxt - timedelta(days=1)


def parse_deadline(text: str, as_of: date) -> str | None:
    """Future deadline: "by June", "kesäkuuhun mennessä", "senast i juni", "in 18 months",
    "om 18 månader", "2027-06"."""
    low = text.lower()
    iso = _ISO_RE.search(low)
    if iso:
        y, m = int(iso.group(1)), int(iso.group(2))
        d = date(y, m, int(iso.group(3))) if iso.group(3) else _end_of_month(y, m)
        return d.isoformat() if d > as_of else None
    m = (re.search(r"\b(?:in|within)\s+(\d{1,3})\s+(months?|years?)\b", low)
         or re.search(r"\b(?:om|inom|på)\s+(\d{1,3})\s+(månad\w*|år\b|åren\b)", low)
         or re.search(r"\b(\d{1,3})\s*(kuukau\w*|kk\b|vuo\w*)", low))
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        months = n * 12 if unit.startswith(("year", "vuo", "år")) else n
        if 0 < months <= 240:
            return add_months(as_of, months).isoformat()
    if re.search(r"\b(in|within) a year\b|\bvuodessa\b|\bvuoden (sisällä|päästä)|\b(om|inom|på) ett år\b", low):
        return add_months(as_of, 12).isoformat()
    mi = _month_index(low)
    if mi:
        month, year = mi
        y = year or (as_of.year if month > as_of.month else as_of.year + 1)
        d = _end_of_month(y, month)
        return d.isoformat() if d > as_of else None
    return None


def parse_period(text: str, as_of: date) -> dict[str, Any]:
    """Past period for spending questions → ``{"period": ...}`` or ``{"start","end"}``."""
    low = text.lower()
    table = (
        (r"last month|previous month|viime kuu|edellisen kuun|edellisessä kuussa|viime kuussa|förra månad|föregående månad", "last_month"),
        (r"this month|so far this month|tässä kuussa|tämän kuun|tällä kuulla|kuluvan kuun|den här månaden|denna månad|i månaden|hittills i månad", "this_month"),
        (r"last week|previous week|viime viiko|edellisellä viikolla|förra veckan|föregående vecka", "last_week"),
        (r"this week|tällä viikolla|tämän viikon|den här veckan|denna vecka|i veckan", "this_week"),
        (r"last 30 days|past 30 days|30 päivä|30 dagar", "last_30_days"),
        (r"(last|past) (3|three) months|(3|kolme|kolmen) (kuukau|kk)|(3|tre) månader", "last_3_months"),
        (r"(last|past) (6|six) months|(6|kuusi|kuuden) (kuukau|kk)|half a year|puoli vuotta|(6|sex) månader|halvår|halvt år", "last_6_months"),
        (r"(last|past) (12|twelve) months|past year|(12|kahdentoista) (kuukau|kk)|vuoden aikana|(12|tolv) månader|senaste året", "last_12_months"),
        (r"this year|tänä vuonna|tämän vuoden|\bi år\b|det här året|detta år", "this_year"),
        (r"last year|viime vuonna|edellisenä vuonna|förra året|i fjol", "last_year"),
    )
    for pattern, period in table:
        if re.search(pattern, low):
            return {"period": period}
    mi = _month_index(low)
    if mi:
        month, year = mi
        y = year or (as_of.year if month <= as_of.month else as_of.year - 1)
        start = date(y, month, 1)
        end = min(_end_of_month(y, month), as_of)
        if start <= as_of:
            return {"start": start.isoformat(), "end": end.isoformat()}
    return {}


# =============================================================================== routing


@dataclass
class Intent:
    name: str
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)


_GOAL_NAMES = {
    "car": {"en": "Car", "fi": "Auto", "sv": "Bil"},
    "travel": {"en": "Trip", "fi": "Matka", "sv": "Resa"},
    "home": {"en": "Home down payment", "fi": "Asunnon käsiraha", "sv": "Egen insats för bostad"},
    "emergency": {"en": "Emergency fund", "fi": "Puskurirahasto", "sv": "Buffert"},
    "education": {"en": "Studies", "fi": "Opinnot", "sv": "Studier"},
    "gadget": {"en": "New gadget", "fi": "Uusi laite", "sv": "Ny pryl"},
    "other": {"en": "Goal", "fi": "Tavoite", "sv": "Mål"},
}

#: intent → pattern (English | Finnish | Swedish). Checked in the order of :func:`route`.
_P = {
    "create_goal": r"\b(create|add|save|set up|make)\b.{0,30}\bgoal\b|\b(luo|lisää|tallenna|tee)\b.{0,30}\btavoit"
                   r"|\b(skapa|lägg till|lägga till|gör|sätt upp)\b.{0,30}\b(spar)?mål",
    "survival": r"surviv|get by|make it (to|until|till)|until payday|till payday|rest of the month|selvi[äy]|selviy|pärjä|loppukuu|palkkapäivään"
                r"|klara(r)? (jag|mig)|klara månaden|överleva|resten av månaden|till lönedagen|fram till lön|pengarna räcka",
    "what_if": r"what if|could i save|would i save|if i (cut|reduce|reduced|stop|stopped|spent less|halve)|\breduc\w* .* by|\bcut\w* .* by|entä jos|säästäisin|vähentäisin|jos vähen|leikkaisin|karsisin|puolittaisin"
               r"|tänk om|vad händer om|skulle jag spara|sparar jag om|om jag (minskar|minskade|skär|skar|drar ner|slutar|slutade|halverar)|\bminska\w* .* med",
    "goal": r"save (up )?for|saving for|save \d|säästä\w*|\bgoal\b|tavoit|spara (ihop )?(till|för)|sparar (till|för)|sparmål|\bmål(et)?\b",
    "goals_list": r"\bmy goals\b|show (my )?goals|tavoitteeni|näytä tavoitteet|mina (spar)?mål|visa (mina )?(spar)?mål",
    "home": r"\bhome\b|\bhouse\b|apartment|mortgage|down payment|asunto|asunn|asuntolaina|käsiraha|omakotitalo|lainahakemu"
            r"|bostad|lägenhet|bolån|egen insats|kontantinsats|eget hem|egnahemshus",
    "safe": r"\bsafe\b|afford|can i (buy|spend)|how much can i spend|turvallise|varaa|voinko (ostaa|käyttää)|paljonko voin käyttää"
            r"|tryggt|har jag råd|kan jag (köpa|använda|spendera)|hur mycket kan jag (använda|spendera|lägga)",
    "profile": r"what kind of spender|spender type|spending personality|spender am i|type of spender|millainen kuluttaja|kuluttajatyyp|kulutustyyp|archetype|arkkityyp"
               r"|hurdan konsument|vilken (typ av|sorts) konsument|vad för (en |slags )?konsument|konsumenttyp|arketyp",
    "benchmark": r"compare|comparison|\bothers\b|peers|people my age|my age|average|normal\b|vertaa|vertailu|muihin|ikätover|ikäisiin|keskivert|keskimäär|mediaani"
                 r"|jämför|jämnårig|i min ålder|\bandra\b|genomsnitt|\bmedel|median",
    "recurring": r"subscription|recurring|standing order|tilaus|tilauk|toistuv|kuukausimaks|prenumeration|abonnemang|återkommande|stående",
    "baskets": r"basket|\bkori|leak|vuod|vuoto|korg|läck",
    "explain": r"what is|what are|what's|what does .* mean|explain|teach me|mikä on|mitä on|mitä tarkoittaa|selitä|opeta"
               r"|vad är|vad betyder|vad innebär|förklara|lär mig",
    "list": r"\b(show|list|biggest|largest|latest|recent)\b.*(transaction|purchase|payment|spend)|näytä .*(osto|tapahtum|maksu)|suurimmat|listaa|viimeisimmät"
            r"|\b(visa|lista|största|senaste)\b.*(transaktion|köp|betalning|utgift)",
    "spending": r"spen[dt]|\bcost|how much|kulu|käytin|käytän|käytetty|maksoin|maksan|paljonko|menee|meni|menot"
                r"|spenderade|spenderar|\blade\b|lägger|lagt|använde|kostade|kostar|hur mycket|utgift|gick åt|går åt",
    "overview": r"balance|saldo|how am i doing|how's my money|overview|miten menee|tilanne|rahatilan|status|hur går det|hur ligger jag till|översikt|läget",
    "deficit": r"menoero|spending gap|utgiftsgap|utgiftsgapet|where does the .*gap|var kommer .*gap|var skillnaden kommer"
               r"|mistä kuuden kuukauden|missä kulutan eniten kuukausittain|kuuden kuukauden menoero",
    "recovery": r"get back (in )?the black|back (in|to) the black|back to (a )?positive|positive balance again"
                r"|plussalle|takaisin plussalle|takaisin vihre|miinuksella|miinussaldo"
                r"|puskurin hupen|puskurin krymp|buffer (from )?shrink|stop my buffer"
                r"|hindrar jag att buffert|bufferten krymp|tillbaka till plus|komma tillbaka till plus|under noll",
}

_CONCEPTS = {
    "three_baskets": r"basket|kori|korg",
    "emergency_fund": r"emergency|buffer|puskuri|hätä|buffert|nödfond",
    "compound_interest": r"compound|korkoa korolle|interest|korko|ränta",
    "pay_yourself_first": r"pay yourself|maksa ensin|betala dig själv",
    "safe_to_spend": r"safe to spend|safe-to-spend|turvallisesti|tryggt att använda",
    "budgeting_50_30_20": r"50/30/20|budget|budjet",
    "inflation": r"inflation|inflaatio",
    "subscriptions": r"subscription|tilaus|prenumeration|abonnemang",
    "investing_basics": r"invest|sijoit|rahasto|stock|osake|etf|placer|fond|aktie",
    "mortgage_basics": r"mortgage|asuntolaina|ltv|bostadslån|bolån",
    "impulse_spending": r"impulse|heräte|impuls",
}


def _has(key: str, low: str) -> bool:
    return re.search(_P[key], low) is not None


def _goal_from_text(text: str, locale: str, as_of: date) -> dict[str, Any] | None:
    amounts = parse_amounts(text)
    if not amounts:
        return None
    kind = guess_goal_kind(text)
    args: dict[str, Any] = {"target_amount": max(amounts), "name": _GOAL_NAMES[kind][norm_locale(locale)]}
    deadline = parse_deadline(text, as_of)
    if deadline:
        args["deadline"] = deadline
    return args


def _spending_filters(text: str) -> dict[str, Any]:
    hit = match_vocabulary(text)
    if not hit:
        return {}
    kind, value = hit
    return {kind: value}


def route(text: str, locale: str, as_of: date, history: list[str] | None = None) -> Intent:
    """Map a user message to tool calls. ``history`` = earlier user messages (newest last)."""
    low = (text or "").lower().strip()

    # 1. explicit goal creation ("create a goal for a car 12000 € by June", "ja, skapa målet")
    if _has("create_goal", low) or re.fullmatch(r"(yes|yep|ok|sure|kyllä|joo|ja|japp|okej)[,!. ]*.*(create|luo|skapa).*", low):
        args = _goal_from_text(text, locale, as_of)
        if not args:
            for prev in reversed(history or []):
                args = _goal_from_text(prev, locale, as_of)
                if args:
                    break
        if args:
            args["kind"] = guess_goal_kind(args["name"])
            return Intent("create_goal", [("create_goal", args)])

    if _has("survival", low):
        amounts = parse_amounts(text)
        args: dict[str, Any] = {"amount": amounts[0]} if amounts else {}
        if not re.search(r"payday|palkka|lön", low):
            until = parse_deadline(text, as_of)  # "…until 5 October" → explicit end date
            if until and not re.search(r"this month|tästä kuusta|tämän kuun|månaden|denna månad", low):
                args["until"] = until
        return Intent("survival", [("survival_plan", args)])

    if _has("what_if", low):
        pct = parse_percent(text) or (50.0 if re.search(r"half|puolit|halver", low) else 20.0)
        filters = _spending_filters(text)
        adj: dict[str, Any] = {"change_pct": -abs(pct)}
        if "category" in filters:
            adj["category"] = filters["category"]
        elif "subcategory" in filters:
            adj["category"] = SUBCATEGORIES[filters["subcategory"]][0]
        elif filters.get("basket") in ("fixed", "irregular", "leak"):
            adj["basket"] = filters["basket"]
        else:
            adj["basket"] = "leak"
        args = {"adjustments": [adj], "horizon_months": 12}
        m = re.search(r"(?:invest|sijoit|placer)\w*.*?(\d+(?:[.,]\d+)?)\s*%", low)
        if m:
            args["invest_return_pct"] = float(m.group(1).replace(",", "."))
            args["horizon_months"] = 60
        return Intent("what_if", [("simulate_what_if", args)])

    if _has("deficit", low):
        # "where does the six-month gap come from" → biggest spending groups, not a this-month list
        end = as_of.replace(day=1) - timedelta(days=1)
        start = add_months(as_of.replace(day=1), -6)
        return Intent("deficit", [("query_spending", {"start": start.isoformat(), "end": end.isoformat(), "group_by": "category"})])

    if _has("recovery", low) and not _has("goal", low):
        # "how do I get back to the black / stop my buffer shrinking": shared recovery data
        return Intent("recovery", [("get_overview", {})])

    if _has("home", low) and not _has("goal", low):
        amounts = [a for a in parse_amounts(text) if a >= 20000]
        return Intent("home", [("home_readiness", {"property_price": amounts[0]} if amounts else {})])

    if _has("safe", low) and not _has("goal", low):
        amounts = parse_amounts(text)
        if amounts and max(amounts) >= 1500:
            # "Can I afford a 12 000 € car?" is a savings-goal question, not a this-week one
            args = _goal_from_text(text, locale, as_of) or {"target_amount": max(amounts)}
            return Intent("plan_goal", [("plan_goal", args)])
        return Intent("safe", [("safe_to_spend", {})])

    if _has("goal", low) and not _has("goals_list", low):
        args = _goal_from_text(text, locale, as_of)
        if args:
            if _has("home", low) and args["target_amount"] >= 50000:
                return Intent("home", [("home_readiness", {"property_price": args["target_amount"]})])
            return Intent("plan_goal", [("plan_goal", args)])
        if re.search(r"goal|tavoit|\bmål", low):
            return Intent("goals", [("list_goals", {})])

    if _has("goals_list", low):
        return Intent("goals", [("list_goals", {})])

    if _has("profile", low):
        return Intent("profile", [("spender_profile", {})])

    if _has("safe", low):
        return Intent("safe", [("safe_to_spend", {})])

    if _has("benchmark", low):
        return Intent("benchmark", [("benchmarks", {})])

    if _has("recurring", low) and not _has("explain", low):
        return Intent("recurring", [("recurring_payments", {})])

    if _has("explain", low):
        topic = next((t for t, p in _CONCEPTS.items() if re.search(p, low)), None)
        if topic == "three_baskets" or (topic is None and _has("baskets", low)):
            calls = [("get_baskets", {"months": 6})]
            if not re.search(r"my (own )?numbers|omilla|minun|mina (egna )?siffror", low):
                calls.append(("explain_concept", {"topic": "three_baskets"}))
            return Intent("baskets", calls)
        if topic:
            return Intent("explain", [("explain_concept", {"topic": topic})])

    if _has("baskets", low):
        return Intent("baskets", [("get_baskets", {"months": 6})])

    filters = _spending_filters(text)
    period = parse_period(text, as_of)
    if _has("list", low):
        args = {**filters, **period, "limit": 10}
        if re.search(r"biggest|largest|suurim|största", low):
            args["sort"] = "largest"
        return Intent("list", [("search_transactions", args)])

    if _has("spending", low) or filters:
        args = {**filters, **(period or {"period": "this_month"})}
        if re.search(r"trend|per month|monthly|by month|over time|kuukausittain|kuukaudessa|kehitys|per månad|månadsvis|utveckling", low):
            args["group_by"] = "month"
            if not period:
                args["period"] = "last_6_months"
        elif not filters:
            args["group_by"] = "category"
        return Intent("spending", [("query_spending", args)])

    return Intent("overview", [("get_overview", {})])


# =============================================================================== templates


def _d(value: Any, loc: str) -> str:
    """Short date: ``25 Sep`` / ``25.9.`` (fi and Finland-Swedish)"""
    d = parse_iso(value)
    if not d:
        return str(value or "")
    return f"{d.day}.{d.month}." if loc in ("fi", "sv") else f"{d.day} {MONTHS_FULL_EN[d.month - 1][:3]}"


def _pct(value: Any) -> int:
    """Accept fractions (0.31) or percents (31) and return a whole percent."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0
    return round(v * 100) if abs(v) <= 1.0 else round(v)


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _b(text: str) -> str:
    return f"**{text}**"


_LEAK_CATEGORIES = {"Restaurants", "Entertainment", "Lifestyle", "Travel"}
_LEAK_SUBCATEGORIES = {"taxi", "fast_food_cafes", "bars", "convenience_store", "restaurants", "cinema", "concerts_events", "clothing", "flights", "hotels"}


def _is_leakish(filters: dict[str, Any]) -> bool:
    """Is this spending filter in the everyday-leaks basket (by the three-baskets rules)?"""
    if filters.get("basket"):
        return filters["basket"] == "leak"
    if filters.get("subcategory"):
        return filters["subcategory"] in _LEAK_SUBCATEGORIES
    return filters.get("category") in _LEAK_CATEGORIES

# closers[tool][persona][loc]
_CLOSERS: dict[str, dict[str, dict[str, str]]] = {
    "query_spending": {
        "sisu": {"en": "Challenge: halve this next week — every skipped purchase is a rep 💪", "fi": "Haaste: puolita tämä ensi viikolla — jokainen väliin jätetty ostos on toisto 💪", "sv": "Utmaning: halvera det här nästa vecka — varje köp du hoppar över är en repetition 💪"},
        "aava": {"en": "Which of these purchases did you enjoy most — and which could you skip without missing them?", "fi": "Mistä näistä ostoksista nautit eniten — ja minkä voisit jättää väliin kaipaamatta?", "sv": "Vilka av de här köpen njöt du mest av — och vilka kunde du hoppa över utan att sakna dem?"},
    },
    "search_transactions": {
        "sisu": {"en": "Challenge: pick one of these you'd skip next time and log the win.", "fi": "Haaste: valitse yksi näistä, jonka jätät ensi kerralla väliin, ja kirjaa voitto.", "sv": "Utmaning: välj ett av de här köpen som du hoppar över nästa gång, och notera vinsten."},
        "aava": {"en": "Looking at the list, do you notice a pattern in when these happen?", "fi": "Huomaatko listassa kuvion siinä, milloin näitä ostoksia syntyy?", "sv": "När du tittar på listan, ser du ett mönster i när de här köpen sker?"},
    },
    "get_baskets": {
        "sisu": {"en": "Challenge: shrink the leak basket by 10 % this month. That's your next PR.", "fi": "Haaste: kutista vuotokoria 10 % tässä kuussa. Se on seuraava ennätyksesi.", "sv": "Utmaning: krymp läckkorgen med 10 % den här månaden. Det blir ditt nästa personbästa."},
        "aava": {"en": "Which of your leaks surprised you the most?", "fi": "Mikä vuodoistasi yllätti sinut eniten?", "sv": "Vilken av dina läckor överraskade dig mest?"},
    },
    "safe_to_spend": {
        "sisu": {"en": "Challenge: stay under your daily amount every day until payday. Streak starts now!", "fi": "Haaste: pysy päivärahan alla joka päivä palkkapäivään asti. Putki alkaa nyt!", "sv": "Utmaning: håll dig under dagsbeloppet varje dag fram till lönedagen. Sviten börjar nu!"},
        "aava": {"en": "Is there one planned purchase this week that could wait until after payday?", "fi": "Voisiko jokin tämän viikon suunnitelluista ostoksista odottaa palkkapäivän yli?", "sv": "Finns det ett planerat köp den här veckan som kunde vänta till efter lönedagen?"},
    },
    "recurring_payments": {
        "sisu": {"en": "Challenge: cancel one subscription you haven't used in 30 days — today.", "fi": "Haaste: peru tänään yksi tilaus, jota et ole käyttänyt 30 päivään.", "sv": "Utmaning: säg upp en prenumeration som du inte har använt på 30 dagar — i dag."},
        "aava": {"en": "Which of these would you sign up for again today?", "fi": "Mihin näistä liittyisit uudelleen tänään?", "sv": "Vilka av de här skulle du teckna igen i dag?"},
    },
    "spender_profile": {
        "sisu": {"en": "Challenge: 7 days without impulse buys. Let's level up your profile!", "fi": "Haaste: 7 päivää ilman heräteostoksia. Nostetaan profiilisi tasoa!", "sv": "Utmaning: 7 dagar utan impulsköp. Nu tar vi din profil till nästa nivå!"},
        "aava": {"en": "Does this feel like you? In which moments do you tend to spend most?", "fi": "Tunnistatko itsesi? Missä tilanteissa yleensä kulutat eniten?", "sv": "Känner du igen dig? I vilka situationer brukar du lägga mest pengar?"},
    },
    "benchmarks": {
        "sisu": {"en": "Challenge: beat the peer median in your biggest category next month.", "fi": "Haaste: alita ikätovereiden mediaani suurimmassa kategoriassasi ensi kuussa.", "sv": "Utmaning: slå jämnårigas median i din största kategori nästa månad."},
        "aava": {"en": "Which comparison matters most to you — and why?", "fi": "Mikä vertailu on sinulle tärkein — ja miksi?", "sv": "Vilken jämförelse betyder mest för dig — och varför?"},
    },
    "simulate_what_if": {
        "sisu": {"en": "Challenge: start the cut today and move the saving to a goal every payday.", "fi": "Haaste: aloita leikkaus tänään ja siirrä säästö tavoitteeseen joka palkkapäivä.", "sv": "Utmaning: börja med nedskärningen i dag och flytta det sparade till ett mål varje lönedag."},
        "aava": {"en": "What would you like that money to do for you a year from now?", "fi": "Mitä haluaisit tuon rahan tekevän puolestasi vuoden päästä?", "sv": "Vad skulle du vilja att de pengarna gör för dig om ett år?"},
    },
    "plan_goal": {
        "sisu": {"en": "Challenge: set the monthly transfer for payday — automatic reps are the best reps.", "fi": "Haaste: ajasta kuukausisiirto palkkapäivälle — automaattiset toistot ovat parhaita.", "sv": "Utmaning: lägg in månadsöverföringen till lönedagen — automatiska repetitioner är de bästa."},
        "aava": {"en": "Which of these changes would feel easiest to start with?", "fi": "Mikä näistä muutoksista tuntuisi helpoimmalta aloittaa?", "sv": "Vilken av de här förändringarna känns lättast att börja med?"},
    },
    "create_goal": {
        "sisu": {"en": "Challenge: make the first deposit this week, however small.", "fi": "Haaste: tee ensimmäinen talletus tällä viikolla, vaikka pieni.", "sv": "Utmaning: gör den första insättningen den här veckan, hur liten den än är."},
        "aava": {"en": "What will reaching this goal mean for you?", "fi": "Mitä tämän tavoitteen saavuttaminen merkitsee sinulle?", "sv": "Vad kommer det att betyda för dig att nå det här målet?"},
    },
    "list_goals": {
        "sisu": {"en": "Challenge: add something to one goal this week. Consistency beats size.", "fi": "Haaste: lisää jotain yhteen tavoitteeseen tällä viikolla. Säännöllisyys voittaa koon.", "sv": "Utmaning: sätt in något på ett mål den här veckan. Regelbundenhet slår storlek."},
        "aava": {"en": "Which goal matters most to you right now?", "fi": "Mikä tavoite on sinulle juuri nyt tärkein?", "sv": "Vilket mål är viktigast för dig just nu?"},
    },
    "survival_plan": {
        "sisu": {"en": "Challenge: cook at home every day until payday. You've got this!", "fi": "Haaste: kokkaa kotona joka päivä palkkapäivään asti. Sinä pystyt tähän!", "sv": "Utmaning: laga mat hemma varje dag fram till lönedagen. Du klarar det här!"},
        "aava": {"en": "Which of these tips feels most doable for you this week?", "fi": "Mikä näistä vinkeistä tuntuu sinusta toteuttamiskelpoisimmalta tällä viikolla?", "sv": "Vilket av de här tipsen känns mest genomförbart för dig den här veckan?"},
    },
    "home_readiness": {
        "sisu": {"en": "Challenge: automate a monthly down-payment transfer — every euro is a rep toward the keys.", "fi": "Haaste: automatisoi kuukausittainen käsirahasiirto — jokainen euro on toisto kohti avaimia.", "sv": "Utmaning: automatisera en månatlig överföring till insatsen — varje euro är en repetition mot nycklarna."},
        "aava": {"en": "What kind of home and timeline would feel right for you?", "fi": "Millainen koti ja aikataulu tuntuisi sinulle oikealta?", "sv": "Vilken sorts bostad och vilken tidtabell skulle kännas rätt för dig?"},
    },
    "explain_concept": {
        "sisu": {"en": "Challenge: explain this to a friend tonight — teaching is the best rep.", "fi": "Haaste: selitä tämä kaverille tänään — opettaminen on paras toisto.", "sv": "Utmaning: förklara det här för en kompis i kväll — att lära ut är den bästa repetitionen."},
        "aava": {"en": "Where do you see this in your own spending?", "fi": "Missä näet tämän omassa kulutuksessasi?", "sv": "Var ser du det här i din egen ekonomi?"},
    },
    "get_overview": {
        "sisu": {"en": "Challenge: check in with me every day this week — streaks build muscle.", "fi": "Haaste: tarkista tilanne kanssani joka päivä tällä viikolla — putket kasvattavat lihaksia.", "sv": "Utmaning: checka in med mig varje dag den här veckan — svitar bygger muskler."},
        "aava": {"en": "What would you most like to change about this month?", "fi": "Mitä haluaisit eniten muuttaa tässä kuussa?", "sv": "Vad skulle du helst vilja ändra på den här månaden?"},
    },
}

# essential (fixed / irregular) spending deserves planning, not cutting
_CLOSERS["query_spending:essential"] = {
    "sisu": {"en": "Challenge: plan next week's essentials with a list — planned reps beat random ones.", "fi": "Haaste: suunnittele ensi viikon välttämättömät ostoslistalla — suunnitellut toistot voittavat satunnaiset.", "sv": "Utmaning: planera nästa veckas nödvändiga inköp med en lista — planerade repetitioner slår slumpmässiga."},
    "aava": {"en": "Is this amount steady from month to month, or does it surprise you sometimes?", "fi": "Pysyykö tämä summa tasaisena kuukaudesta toiseen, vai yllättääkö se joskus?", "sv": "Håller sig den här summan jämn från månad till månad, eller överraskar den ibland?"},
}

# a goal plan for someone who spends more than they earn: no "set the transfer" push
_CLOSERS["plan_goal:deficit"] = {
    "sisu": {"en": "Challenge: pick one cut from the plan and hold it for the next 30 days.", "fi": "Haaste: valitse suunnitelmasta yksi leikkaus ja pidä siitä kiinni seuraavat 30 päivää.", "sv": "Utmaning: välj en nedskärning ur planen och håll fast vid den i 30 dagar."},
    "aava": {"en": "Which of these costs would be the easiest to bring down first?", "fi": "Mikä näistä menoista olisi helpoin saada ensin pienemmäksi?", "sv": "Vilken av de här utgifterna vore lättast att få ner först?"},
}

# recovery answer: a small concrete step, never a savings-streak or "pay yourself first" push
_CLOSERS["get_overview:recovery"] = {
    "sisu": {"en": "One small step today: list bills due before payday and check which are essential.", "fi": "Yksi pieni askel tänään: listaa ennen palkkapäivää erääntyvät laskut ja tarkista, mitkä ovat välttämättömiä.", "sv": "Ett litet steg i dag: lista räkningar som förfaller före lönedagen och kontrollera vilka som är nödvändiga."},
    "aava": {"en": "If this feels heavy, we can take one bill or one essential at a time — where would you like to start?", "fi": "Jos tilanne tuntuu raskaalta, voidaan ottaa yksi lasku tai meno kerrallaan — mistä haluaisit aloittaa?", "sv": "Om det känns tungt kan vi ta en räkning eller en nödvändig utgift i taget — var vill du börja?"},
}

_CLOSERS["query_spending:deficit"] = {
    "sisu": {"en": "Check which costs are essential before choosing a change.", "fi": "Tarkista, mitkä menot ovat välttämättömiä, ennen kuin valitset muutoksen.", "sv": "Kontrollera vilka utgifter som är nödvändiga innan du väljer en ändring."},
    "aava": {"en": "Which costs could change without compromising essentials?", "fi": "Missä menoissa voisi joustaa vaarantamatta välttämättömiä tarpeita?", "sv": "Vilka utgifter kunde ändras utan att äventyra det nödvändiga?"},
}

_CONCEPT_LINES: dict[str, dict[str, str]] = {
    "get_overview:recovery": {"en": "💡 The six-month average describes the comparison period, not a promise for this month — a payday balance is a snapshot.", "fi": "💡 Kuuden kuukauden keskiarvo kuvaa vertailujaksoa, ei lupaa tämän kuun tulosta — palkkapäivän saldo on hetken tilanne.", "sv": "💡 Sexmånadersgenomsnittet beskriver jämförelseperioden, inte ett löfte för den här månaden — saldot på lönedagen är en ögonblicksbild."},
    "plan_goal:deficit": {"en": "💡 Saving starts once less goes out than comes in — close the gap first, then automate the transfer.", "fi": "💡 Säästäminen alkaa, kun rahaa lähtee vähemmän kuin tulee — kuro ensin vaje umpeen ja automatisoi siirto vasta sitten.", "sv": "💡 Sparandet börjar när det går ut mindre än det kommer in — täpp till underskottet först och automatisera överföringen sedan."},
    "query_spending:essential": {"en": "💡 Essentials are best managed by planning and comparing prices, not by willpower.", "fi": "💡 Välttämättömiä menoja hallitaan parhaiten suunnittelulla ja hintavertailulla, ei tahdonvoimalla.", "sv": "💡 Nödvändiga utgifter sköts bäst med planering och prisjämförelser, inte med viljestyrka."},
    "query_spending": {"en": "💡 Leaks are small, frequent purchases — harmless one by one, often the biggest lever together.", "fi": "💡 Vuodot ovat pieniä, toistuvia ostoksia — yksittäin harmittomia, yhdessä usein budjetin suurin vipu.", "sv": "💡 Läckor är små, täta köp — ofarliga ett och ett, men tillsammans ofta budgetens största hävstång."},
    "safe_to_spend": {"en": "💡 Your balance isn't your spending money: bills due before payday come first.", "fi": "💡 Saldo ei ole käyttörahaa: ennen palkkapäivää erääntyvät laskut menevät edelle.", "sv": "💡 Ditt saldo är inte dina fickpengar: räkningar som förfaller före lönedagen går först."},
    "simulate_what_if": {"en": "💡 Habit changes compound: a small cut repeats every single month.", "fi": "💡 Tapamuutokset kertautuvat: pieni leikkaus toistuu joka ikinen kuukausi.", "sv": "💡 Nya vanor växer med tiden: en liten nedskärning upprepas varenda månad."},
    "plan_goal": {"en": "💡 Pay yourself first: move the goal money on payday, before you spend.", "fi": "💡 Maksa ensin itsellesi: siirrä tavoiteraha palkkapäivänä ennen kuin kulutat.", "sv": "💡 Betala dig själv först: flytta målpengarna på lönedagen, innan du börjar handla."},
    "survival_plan": {"en": "💡 An emergency fund turns the next tight month into a non-event.", "fi": "💡 Puskurirahasto tekee seuraavasta tiukasta kuusta pelkän sivujuonteen.", "sv": "💡 En buffert gör nästa tighta månad till en icke-händelse."},
    "spender_profile": {"en": "💡 Spending follows habits more than income — knowing your pattern is half the fix.", "fi": "💡 Kulutus seuraa tapoja enemmän kuin tuloja — oman kuvion tunteminen on puoli ratkaisua.", "sv": "💡 Utgifter följer vanor mer än inkomster — att känna sitt mönster är halva lösningen."},
    "benchmarks": {"en": "💡 Peer averages are a mirror, not a rule — your goals decide what's right for you.", "fi": "💡 Vertailu on peili, ei sääntö — omat tavoitteesi ratkaisevat, mikä on sinulle oikein.", "sv": "💡 Jämförelser är en spegel, inte en regel — dina mål avgör vad som är rätt för dig."},
    "get_baskets": {"en": "💡 Trim leaks first, plan for irregulars, keep fixed costs lean.", "fi": "💡 Karsi ensin vuodot, varaudu epäsäännöllisiin ja pidä kiinteät kulut kurissa.", "sv": "💡 Täpp till läckorna först, planera för de oregelbundna och håll de fasta kostnaderna smala."},
    "home_readiness": {"en": "💡 Banks look at steady saving as much as at the down payment itself.", "fi": "💡 Pankki katsoo säännöllistä säästämistä yhtä tarkasti kuin itse käsirahaa.", "sv": "💡 Banken tittar lika noga på regelbundet sparande som på själva insatsen."},
    "recurring_payments": {"en": "💡 Subscriptions are designed to be forgotten — review them every few months.", "fi": "💡 Tilaukset on suunniteltu unohtumaan — käy ne läpi muutaman kuukauden välein.", "sv": "💡 Prenumerationer är gjorda för att glömmas bort — gå igenom dem med några månaders mellanrum."},
}


def _t_query_spending(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    what = payload.get("what") or ""
    period = (payload.get("period") or {}).get("label", "")
    total, count = _f(payload.get("total")), int(_f(payload.get("count")))
    groups = payload.get("groups") or []
    filters = payload.get("filters") or {}
    cat, sub, basket = filters.get("category"), filters.get("subcategory"), filters.get("basket")
    stem = fi_cost_stem(cat, sub, basket)
    fi_when = fi_inessive_period(period)
    fi_costs = f"{stem}kulut".capitalize() if stem else "Kulusi"
    sv_on = "" if what in ("", "allt") else f" på {what}"
    if payload.get("group_by") in ("category", "basket", "merchant") and groups:
        top = groups[0]
        if loc == "fi":
            text = f"{fi_costs} {fi_when}: yhteensä {_b(fmt_eur(total, loc))} ({count} ostosta). Suurin erä: {top['label']} {fmt_eur(top['total'], loc)}."
        elif loc == "sv":
            text = f"Du har lagt {_b(fmt_eur(total, loc))}{sv_on} under {period}, fördelat på {count} köp. Största posten: {top['label']} {fmt_eur(top['total'], loc)}."
        else:
            text = f"You spent {_b(fmt_eur(total, loc))} in {period} across {count} purchases. Biggest: {top['label']} at {fmt_eur(top['total'], loc)}."
    elif payload.get("group_by") == "month" and groups:
        peak = max(groups, key=lambda g: _f(g["total"]))
        if loc == "fi":
            text = f"{fi_costs} {fi_when}: yhteensä {_b(fmt_eur(total, loc))}. Kallein kuukausi oli {peak['label']} ({fmt_eur(peak['total'], loc)})."
        elif loc == "sv":
            text = f"Utgifter{sv_on} under {period}: totalt {_b(fmt_eur(total, loc))}. Dyraste månaden var {peak['label']} ({fmt_eur(peak['total'], loc)})."
        else:
            text = f"{what.capitalize()}: {_b(fmt_eur(total, loc))} in total over {period}. Peak month was {peak['label']} at {fmt_eur(peak['total'], loc)}."
    elif count == 0:
        if loc == "fi":
            text = f"{fi_costs} {fi_when}: 0 € — ei yhtään ostosta. Hienoa!"
        elif loc == "sv":
            text = f"Inga köp alls{sv_on} under {period} — 0 €. Snyggt!"
        else:
            text = f"No {what} spending in {period} at all — 0 €. Nice!"
        return text, "positive"
    else:
        if loc == "fi":
            text = f"{fi_costs} {fi_when}: {_b(fmt_eur(total, loc))} — {count} ostosta, keskimäärin {fmt_eur(payload.get('avg_tx'), loc)}."
        elif loc == "sv":
            text = f"Du lade {_b(fmt_eur(total, loc))}{sv_on} under {period} — {count} köp, i snitt {fmt_eur(payload.get('avg_tx'), loc)}."
        else:
            text = f"You spent {_b(fmt_eur(total, loc))} on {what} in {period} — {count} purchases, {fmt_eur(payload.get('avg_tx'), loc)} on average."
    if _is_leakish(filters):
        text += " " + pick(loc, "That's in your everyday-leaks basket: optional spending that adds up quietly.",
                           "Tämä kuuluu arjen vuotoihin: valinnaista kulutusta, joka kertyy huomaamatta.",
                           "Det hör till korgen vardagsläckor: valfria utgifter som växer i det tysta.")
        return text, "concern" if total > 100 else "neutral"
    return text, "neutral"


def _t_search_transactions(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    n = int(_f(payload.get("shown")))
    what = payload.get("what") or ""
    total = fmt_eur(abs(_f(payload.get("shown_total"))), loc)
    items = payload.get("items") or []
    if not n:
        return pick(loc, "I couldn't find matching transactions.", "En löytänyt tapahtumia näillä ehdoilla.",
                    "Jag hittade inga transaktioner som matchar."), "neutral"
    first = items[0]
    if loc == "fi":
        label = "" if what == "tapahtumat" else f" ({what})"
        return f"Tässä {n} tapahtumaa{label}, yhteensä {_b(total)}. Ensimmäisenä: {first.get('label')} {fmt_eur(abs(_f(first.get('amount'))), loc)} ({_d(first.get('date'), loc)}).", "neutral"
    if loc == "sv":
        label = "" if what == "transaktioner" else f" ({what})"
        return f"Här är {n} transaktioner{label}, totalt {_b(total)}. Överst på listan: {first.get('label')} {fmt_eur(abs(_f(first.get('amount'))), loc)} ({_d(first.get('date'), loc)}).", "neutral"
    noun = "transactions" if what == "transactions" else f"{what} transactions"
    return f"Here are {n} {noun}, {_b(total)} in total. Top of the list: {first.get('label')} at {fmt_eur(abs(_f(first.get('amount'))), loc)} on {_d(first.get('date'), loc)}.", "neutral"


def _t_get_baskets(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    cur = payload.get("current_month") or {}
    shares = payload.get("shares_pct") or {}
    top_leak = ((payload.get("top") or {}).get("leak") or [{}])[0]
    f, i, l = (fmt_eur(abs(_f(cur.get(b))), loc) for b in ("fixed", "irregular", "leak"))
    fs, ls = round(_f(shares.get("fixed"))), round(_f(shares.get("leak")))
    if loc == "fi":
        text = f"Tässä kuussa: kiinteät {_b(f)} ({fs} %), epäsäännölliset {i} ja arjen vuodot {_b(l)} ({ls} %)."
        if top_leak.get("label"):
            text += f" Suurin vuoto: {top_leak['label']} {fmt_eur(abs(_f(top_leak.get('total'))), loc)}."
    elif loc == "sv":
        text = f"Den här månaden: fasta måsten {_b(f)} ({fs} %), oregelbundna måsten {i} och vardagsläckor {_b(l)} ({ls} %)."
        if top_leak.get("label"):
            text += f" Största läckan: {top_leak['label']} {fmt_eur(abs(_f(top_leak.get('total'))), loc)}."
    else:
        text = f"This month: fixed essentials {_b(f)} ({fs} %), irregular essentials {i}, everyday leaks {_b(l)} ({ls} %)."
        if top_leak.get("label"):
            text += f" Biggest leak: {top_leak['label']} at {fmt_eur(abs(_f(top_leak.get('total'))), loc)}."
    return text, "concern" if _f(shares.get("leak")) >= 35 else "neutral"


def _t_safe_to_spend(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    status = raw.get("status")
    per_day, week = fmt_eur(raw.get("safe_per_day"), loc), fmt_eur(raw.get("safe_this_week"), loc)
    days, payday = raw.get("days_until_payday"), _d(raw.get("next_payday"), loc)
    bills = raw.get("upcoming_bills") or []
    bills_total = fmt_eur(sum(abs(_f(b.get("amount"))) for b in bills), loc)
    if loc == "fi":
        text = f"Voit käyttää turvallisesti {_b(per_day + ' päivässä')} — tällä viikolla {week} — palkkapäivään {payday} asti ({days} pv)."
        if bills:
            text += f" Ennen sitä erääntyy vielä laskuja {bills_total}."
        if status == "critical":
            text += " Tilanne on tiukka: vältä nyt kaikkia ei-välttämättömiä ostoksia."
    elif loc == "sv":
        text = f"Du kan tryggt använda {_b(per_day + ' per dag')} — {week} den här veckan — fram till lönedagen {payday} ({days} dagar)."
        if bills:
            text += f" Före det förfaller ännu räkningar på {bills_total}."
        if status == "critical":
            text += " Läget är tight: hoppa över allt som inte är nödvändigt just nu."
    else:
        text = f"You can safely spend {_b(per_day + ' a day')} — {week} this week — until payday on {payday} ({days} days)."
        if bills:
            text += f" Bills of {bills_total} are still due before then."
        if status == "critical":
            text += " Things are tight: skip anything non-essential for now."
    return text, {"critical": "concern", "comfortable": "positive"}.get(str(status), "neutral")


def _t_recurring_payments(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    items = payload.get("items") or []
    n, total = len(raw.get("items") or items), fmt_eur(abs(_f(payload.get("monthly_total"))), loc)
    top = max(items, key=lambda i: abs(_f(i.get("avg_amount"))), default=None)
    top_amt = fmt_eur(abs(_f(top.get("avg_amount"))), loc) if top else ""
    if loc == "fi":
        text = f"Sinulla on {n} toistuvaa maksua, yhteensä noin {_b(total + ' kuukaudessa')}."
        if top:
            text += f" Suurin: {top.get('label')} {top_amt}."
    elif loc == "sv":
        text = f"Du har {n} återkommande betalningar, sammanlagt ungefär {_b(total + ' i månaden')}."
        if top:
            text += f" Störst: {top.get('label')} {top_amt}."
    else:
        text = f"You have {n} recurring payments, about {_b(total + ' a month')}."
        if top:
            text += f" Biggest: {top.get('label')} at {top_amt}."
    return text, "neutral"


def _t_spender_profile(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    arch = raw.get("archetype") or {}
    name = f"{arch.get('emoji', '')} {arch.get('name', '')}".strip()
    leak, sav, weekend = _pct(raw.get("leak_share")), _pct(raw.get("savings_rate")), _pct(raw.get("weekend_share"))
    if loc in ARCHETYPE_L10N:
        l10n_name, l10n_desc = ARCHETYPE_L10N[loc].get(str(arch.get("key")), (arch.get("name", ""), ""))
        name = f"{arch.get('emoji', '')} {l10n_name}".strip()
    if loc == "fi":
        text = f"Olet {_b(name)}: {l10n_desc} Vuotojen osuus kulutuksesta on {leak} %, säästöaste {sav} % ja viikonloppujen osuus {weekend} %."
    elif loc == "sv":
        text = f"Du är {_b(name)}: {l10n_desc} Läckorna står för {leak} % av dina utgifter, din sparkvot är {sav} % och helgerna tar {weekend} %."
    else:
        text = f"You're a {_b(name)}: {arch.get('description', '')} Leaks are {leak} % of your spending, your savings rate is {sav} % and weekends take {weekend} %."
    tone = "concern" if arch.get("key") == "tightrope_walker" else ("positive" if arch.get("key") in ("steady_planner", "squirrel_saver") else "neutral")
    return text, tone


def _t_benchmarks(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    band = (raw.get("peer_group") or {}).get("age_band") or ""
    cats = [c for c in raw.get("categories") or [] if c.get("percentile") is not None]
    if not cats:
        return pick(loc, "I couldn't find comparison data.", "Vertailutietoa ei löytynyt.",
                    "Jag hittade ingen jämförelsedata."), "neutral"
    high = max(cats, key=lambda c: _f(c.get("percentile")))
    low = min(cats, key=lambda c: _f(c.get("percentile")))
    hi_cat, lo_cat = category_label(high.get("category"), loc), category_label(low.get("category"), loc)
    you, med, rank = fmt_eur(high.get("you_monthly"), loc), fmt_eur(high.get("peer_median_monthly"), loc), _pct_rank(high.get("percentile"))
    lean = fmt_eur(low.get("you_monthly"), loc)
    if loc == "fi":
        text = (
            f"Verrattuna ikätovereihisi (ikä {band}): {hi_cat} {_b(you + '/kk')} "
            f"vs. mediaani {med} — olet {rank}. persentiilissä. "
            f"Edullisin alueesi: {lo_cat} ({lean}/kk)."
        )
    elif loc == "sv":
        text = (
            f"Jämfört med jämnåriga (ålder {band}): {hi_cat} {_b(you + '/mån.')} "
            f"mot en median på {med} — du ligger på {rank}:e percentilen. "
            f"Där lägger du minst: {lo_cat} ({lean}/mån.)."
        )
    else:
        text = (
            f"Compared with your peers (age {band}): {hi_cat} is {_b(you + '/month')} "
            f"vs a median of {med} — the {rank}th percentile. "
            f"Your leanest area: {lo_cat} at {lean}/month."
        )
    return text, "concern" if _pct(high.get("percentile")) >= 75 else "neutral"


def _pct_rank(value: Any) -> int:
    return _pct(value)


def _t_simulate_what_if(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    adj = (payload.get("adjustments") or [{}])[0]
    target = adj.get("category") or adj.get("basket") or ""
    target_txt = BASKET_LABEL.get(target, {}).get(loc) if target in BASKET_LABEL else category_label(target, loc)
    pct = abs(round(_f(adj.get("change_pct"))))
    monthly, total, horizon = fmt_eur(raw.get("monthly_saving"), loc), fmt_eur(raw.get("total_saving"), loc), raw.get("horizon_months", 12)
    with_ret = raw.get("with_return")
    grows = bool(with_ret and _f(with_ret) > _f(raw.get("total_saving")))
    if loc == "fi":
        stem = fi_cost_stem(adj.get("category"), None, adj.get("basket"))
        target_fi = f"{stem}kuluja" if stem else target_txt
        text = f"Jos vähennät {target_fi} {pct} %, säästät noin {_b(monthly + ' kuukaudessa')} — {_b(total)} {horizon} kuukaudessa."
        if grows:
            text += f" Sijoitettuna esimerkkituotolla summa olisi {fmt_eur(with_ret, loc)} (tuotto ei ole taattu)."
    elif loc == "sv":
        target_sv = f"dina {target_txt}" if target in BASKET_LABEL else f"dina utgifter för {target_txt}"
        text = f"Om du minskar {target_sv} med {pct} % sparar du ungefär {_b(monthly + ' i månaden')} — {_b(total)} på {horizon} månader."
        if grows:
            text += f" Placerat med exempelavkastningen kunde summan bli {fmt_eur(with_ret, loc)} (avkastningen är aldrig garanterad)."
    else:
        text = f"Cutting {target_txt} by {pct} % saves about {_b(monthly + ' a month')} — {_b(total)} over {horizon} months."
        if grows:
            text += f" Invested at the example return it could reach {fmt_eur(with_ret, loc)} (returns are never guaranteed)."
    return text, "positive"


def _t_plan_goal(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    name = raw.get("name") or pick(loc, "your goal", "tavoite", "ditt mål")
    target, need = fmt_eur(raw.get("target_amount"), loc), fmt_eur(raw.get("needed_per_month"), loc)
    surplus = fmt_eur(raw.get("current_monthly_surplus"), loc)
    deadline = raw.get("deadline") or raw.get("suggested_deadline")
    dl = parse_iso(deadline)
    feas = raw.get("feasibility")
    cuts = raw.get("cuts") or []
    fe_txt = {
        "en": {"on_track": "you're on track", "stretch": "it's a stretch, but doable with a few cuts", "unrealistic": "that timeline is too tight"},
        "fi": {"on_track": "olet aikataulussa", "stretch": "se vaatii venymistä, mutta onnistuu muutamalla leikkauksella", "unrealistic": "aikataulu on liian tiukka"},
        "sv": {"on_track": "du ligger i fas", "stretch": "det kräver lite ansträngning men går med några nedskärningar", "unrealistic": "tidtabellen är för snäv"},
    }[loc].get(str(feas), "")
    # An overspender has no surplus to save from: say that plainly instead of printing a
    # negative "surplus", and do not push the 'Create goal' button on a plan that cannot work.
    deficit = -_f(raw.get("current_monthly_surplus"))
    short = fmt_eur(deficit, loc, 0)
    blocked = deficit > 0 and feas == "unrealistic"
    # deficit + the goal's monthly need, stated separately from the goal alone
    combined = fmt_eur(deficit + _f(raw.get("needed_per_month")), loc, 0) if blocked else ""
    if loc == "fi":
        state = (f"Tällä hetkellä rahaa lähtee noin {short}/kk enemmän kuin tulee, joten säästettävää ei vielä jää."
                 if deficit > 0 else f"Nykyinen ylijäämäsi on {surplus}/kk, joten {fe_txt}.")
        text = f"{name} {_b(target)}" + (f" {_d(deadline, loc)}{dl.year if dl else ''} mennessä" if deadline else "") + f": tarvitset {_b(need + '/kk')}. {state}"
        if cuts:
            c = cuts[0]
            text += f" Isoin apu: {c.get('label') or category_label(c.get('category'), loc)} −{round(_f(c.get('cut_pct')))} % → {fmt_eur(c.get('monthly_saving'), loc)}/kk."
        if feas == "unrealistic" and raw.get("suggested_deadline"):
            text += f" Realistisempi takaraja: {raw['suggested_deadline']}."
        text += (" Aloita kuromalla tämä kuukausittainen vaje umpeen, niin tavoitteesta tulee realistinen."
                 if blocked else " Napauta 'Luo tavoite', niin tallennan sen.")
        if blocked:
            text += f" Alijäämä mukaan lukien kuukausitarve on yhteensä {combined}/kk."
    elif loc == "sv":
        state = (f"Just nu går det ut ungefär {short}/mån. mer än det kommer in, så det blir inget över att spara ännu."
                 if deficit > 0 else f"Ditt nuvarande överskott är {surplus}/mån., så {fe_txt}.")
        text = f"{name} {_b(target)}" + (f" senast {_d(deadline, loc)}{dl.year if dl else ''}" if deadline else "") + f": du behöver {_b(need + '/mån.')} {state}"
        if cuts:
            c = cuts[0]
            text += f" Största hävstången: {c.get('label')} −{round(_f(c.get('cut_pct')))} % → {fmt_eur(c.get('monthly_saving'), loc)}/mån."
        if feas == "unrealistic" and raw.get("suggested_deadline"):
            text += f" Ett realistiskt slutdatum vore {_d(raw['suggested_deadline'], loc)}{parse_iso(raw['suggested_deadline']).year if parse_iso(raw['suggested_deadline']) else ''}."
        text += (" Börja med att täppa till det månatliga underskottet, så blir målet realistiskt."
                 if blocked else " Tryck på knappen 'Skapa målet', så sparar jag det.")
        if blocked:
            text += f" Underskottet plus månadsbehovet blir sammanlagt {combined}/mån."
    else:
        state = (f"Right now about {short}/month more goes out than comes in, so there is nothing spare to save yet."
                 if deficit > 0 else f"Your current surplus is {surplus}/month, so {fe_txt}.")
        text = f"{name} — {_b(target)}" + (f" by {_d(deadline, loc)} {dl.year if dl else ''}" if deadline else "") + f": you need {_b(need + '/month')}. {state}"
        if cuts:
            c = cuts[0]
            text += f" Biggest lever: {c.get('label')} −{round(_f(c.get('cut_pct')))} % → {fmt_eur(c.get('monthly_saving'), loc)}/month."
        if feas == "unrealistic" and raw.get("suggested_deadline"):
            text += f" A realistic deadline would be {raw['suggested_deadline']}."
        text += (" Start by closing that monthly gap; then the goal becomes realistic."
                 if blocked else " Tap 'Create goal' to save it.")
        if blocked:
            text += f" The deficit plus the monthly need is {combined}/month in total."
    return text, {"on_track": "positive", "unrealistic": "concern"}.get(str(feas), "neutral")


def _t_create_goal(raw: Any, payload: dict[str, Any], loc: str) -> tuple[str, str]:
    goal = payload.get("goal") or {}
    name, amount = _b(str(goal.get("name"))), fmt_eur(goal.get("target_amount"), loc)
    if payload.get("status") == "saved":
        return pick(loc, f"Saved! {name} — {amount} is now in your goals 🎉",
                    f"Tallennettu! Tavoite {name} {amount} on nyt tavoitteissasi 🎉",
                    f"Sparat! Målet {name} på {amount} finns nu bland dina mål 🎉"), "positive"
    return pick(loc, f"Ready to save: {name} — {amount}. Tap the button to confirm.",
                f"Valmis tallennettavaksi: {name} {amount}. Napauta painiketta vahvistaaksesi.",
                f"Klart att spara: {name} — {amount}. Tryck på knappen för att bekräfta."), "neutral"


def _t_list_goals(raw: Any, payload: dict[str, Any], loc: str) -> tuple[str, str]:
    goals = payload.get("goals") or []
    if not goals:
        return pick(loc, "You don't have any goals yet. Tell me what you'd like to save for!",
                    "Sinulla ei ole vielä tavoitteita. Kerro, mihin haluaisit säästää!",
                    "Du har inga sparmål ännu. Berätta vad du vill spara till!"), "neutral"
    parts = [f"{g.get('name')} {_pct(g.get('progress'))} %" for g in goals[:3]]
    return pick(loc, "Your goals: ", "Tavoitteesi: ", "Dina mål: ") + ", ".join(parts) + ".", "neutral"


def _t_survival_plan(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    amount, until, days = fmt_eur(raw.get("amount"), loc), _d(raw.get("until"), loc), raw.get("days")
    bills, free = fmt_eur(raw.get("upcoming_bills_total"), loc), fmt_eur(raw.get("free_money"), loc)
    per_day, per_week = fmt_eur(raw.get("per_day"), loc), fmt_eur(raw.get("per_week"), loc)
    risk = raw.get("risk")
    tips = raw.get("tips") or []
    no_bills = _f(raw.get("upcoming_bills_total")) == 0
    short = fmt_eur(raw.get("shortfall"), loc) if risk == "short" and raw.get("shortfall") else ""
    if loc == "fi":
        bills_txt = "laskuja ei ole enää erääntymässä" if no_bills else f"laskuja on vielä {bills}"
        text = f"{amount} {until} asti ({days} pv): {bills_txt}, joten vapaata rahaa jää {_b(free)} — {_b(per_day + ' päivässä')} eli {per_week} viikossa."
        if short:
            text += f" Rahaa puuttuu {short}, joten priorisoi vuokra, ruoka ja laskut."
    elif loc == "sv":
        bills_txt = "inga räkningar förfaller längre" if no_bills else f"räkningar på {bills} förfaller ännu"
        text = f"Med {amount} fram till {until} ({days} dagar): {bills_txt}, så du har {_b(free)} fritt — {_b(per_day + ' per dag')} eller {per_week} i veckan."
        if short:
            text += f" Det fattas {short}, så prioritera hyra, mat och räkningar."
    else:
        bills_txt = "no bills are still due" if no_bills else f"bills still due are {bills}"
        text = f"With {amount} until {until} ({days} days): {bills_txt}, leaving {_b(free)} — {_b(per_day + ' a day')} or {per_week} a week."
        if short:
            text += f" You're {short} short, so put rent, food and bills first."
    if tips:  # analytics tips come back in the turn language (app.i18n)
        text += " " + str(tips[0])
    return text, {"short": "concern", "ok": "positive"}.get(str(risk), "neutral")


def _t_home_readiness(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    verdict = raw.get("verdict")
    price, equity, yours = fmt_eur(raw.get("property_price"), loc), fmt_eur(raw.get("equity_needed"), loc), fmt_eur(raw.get("your_equity_estimate"), loc)
    req_inc, inc = fmt_eur(raw.get("required_monthly_income"), loc), fmt_eur(raw.get("your_monthly_income"), loc)
    gaps = raw.get("gaps") or []
    v_txt = {
        "en": {"ready": "you look ready", "almost": "you're almost there", "not_yet": "not quite yet"},
        "fi": {"ready": "näytät olevan valmis", "almost": "olet melkein valmis", "not_yet": "et ole vielä aivan valmis"},
        "sv": {"ready": "ser du ut att vara redo", "almost": "är du nästan där", "not_yet": "är du inte riktigt där ännu"},
    }[loc].get(str(verdict), "")
    if loc == "fi":
        text = f"{price} asuntoon {v_txt}: omarahoitusta tarvitaan {_b(equity)} (arviosi {yours}) ja tuloja noin {req_inc}/kk (sinulla {inc}/kk)."
    elif loc == "sv":
        text = f"För en bostad för {price} {v_txt}: du behöver {_b(equity)} i egen insats (du har ungefär {yours}) och en inkomst på cirka {req_inc}/mån. (din: {inc}/mån.)."
    else:
        text = f"For a {price} home {v_txt}: you'd need {_b(equity)} of your own money (you have about {yours}) and roughly {req_inc}/month income (yours: {inc}/month)."
    if gaps:  # analytics gap texts come back in the turn language (app.i18n)
        text += " " + str(gaps[0])
    return text, {"ready": "positive", "not_yet": "concern"}.get(str(verdict), "neutral")


def _t_explain_concept(raw: Any, payload: dict[str, Any], loc: str) -> tuple[str, str]:
    lesson = raw if isinstance(raw, dict) else {}
    return f"{lesson.get('emoji', '💡')} {_b(str(payload.get('title')))}: {payload.get('key_points', '')}", "neutral"


def _recovery_sentence(rec: dict[str, Any], loc: str) -> tuple[str, str]:
    """Honest recovery summary from the shared computation (balance + 6-month cashflow)."""
    if rec.get("state") == "unknown":
        return pick(loc, "There is not enough information to assess your situation.",
                    "Tietoja ei ole riittävästi tilanteen arvioimiseen.",
                    "Det finns inte tillräckligt med information för att bedöma läget."), "neutral"
    months = rec.get("months") or 6
    surplus, deficit = _f(rec.get("monthly_surplus")), _f(rec.get("deficit"))
    need, planned = _f(rec.get("goal_monthly_need")), rec.get("planned_monthly_change")
    if surplus < 0:
        trend = pick(loc,
                     f"Over the last {months} full months spending has averaged {_b(fmt_eur(deficit, loc))} more than income.",
                     f"Viimeisten {months} täyden kuukauden aikana menoja on ollut keskimäärin {_b(fmt_eur(deficit, loc))} tuloja enemmän.",
                     f"Under de senaste {months} hela månaderna har utgifterna varit i genomsnitt {_b(fmt_eur(deficit, loc))} mer än inkomsten.")
    else:
        trend = pick(loc,
                     f"The last {months} full months averaged a surplus of {fmt_eur(surplus, loc)}/month. We should check the current situation separately.",
                     f"Kuuden täyden kuukauden ylijäämä oli keskimäärin {fmt_eur(surplus, loc)}/kk. Tarkistetaan nykytilanne erikseen.",
                     f"De senaste {months} hela månaderna gav ett överskott på i genomsnitt {fmt_eur(surplus, loc)}/mån. Vi kontrollerar nuläget separat.")
    text = " " + trend
    if surplus < 0 and need > 0 and planned:
        text += pick(loc,
                     f" The goal needs {fmt_eur(need, loc)}/month, which is not enough alone — with the deficit the planned change is {_b(fmt_eur(planned, loc) + '/month')}.",
                     f" Tavoitteelle {fmt_eur(need, loc)}/kk ei yksin riitä — alijäämä mukaan lukien muutos on {_b(fmt_eur(planned, loc) + '/kk')}.",
                     f" Målet behöver {fmt_eur(need, loc)}/mån., vilket inte räcker ensamt — med underskottet är den planerade ändringen {_b(fmt_eur(planned, loc) + '/mån.')}.")
    text += pick(loc, " Start with everyday essentials and bills, not a savings challenge.",
                 " Aloitetaan arjen välttämättömistä menoista ja laskuista, ei säästöhaasteesta.",
                 " Vi börjar med vardagens nödvändiga utgifter och räkningar, inte med en sparutmaning.")
    if rec.get("goal_reservations_present"):
        text += pick(loc,
                     f" The calculation includes {fmt_eur(rec.get('goal_contributions'), loc)} reserved for goals until payday.",
                     f" Laskelma sisältää tavoitevarauksia {fmt_eur(rec.get('goal_contributions'), loc)} palkkapäivään asti.",
                     f" Beräkningen inkluderar {fmt_eur(rec.get('goal_contributions'), loc)} reserverat för mål fram till lönedagen.")
    return text, "concern"


def _t_get_overview(raw: dict[str, Any], payload: dict[str, Any], loc: str) -> tuple[str, str]:
    month = raw.get("month") or {}
    sts = raw.get("safe_to_spend") or {}
    inc, out = fmt_eur(month.get("income"), loc), fmt_eur(month.get("spent"), loc)
    per_day = fmt_eur(sts.get("safe_per_day"), loc) if sts else ""
    rec = raw.get("recovery") or {}
    if rec.get("state") == "unknown":
        return _recovery_sentence(rec, loc)
    recovery = rec.get("state") in ("balance_repair", "cashflow_stabilizing")
    # a recovery answer states the balance to the cent: it is the number the advice turns on
    bal = fmt_eur(raw.get("balance"), loc, 2) if recovery else fmt_eur(raw.get("balance"), loc)
    if loc == "fi":
        text = f"Saldosi on {_b(bal)}. Tässä kuussa tuloja {inc} ja kuluja {out}."
        if sts and not recovery:
            text += f" Turvallisesti käytettävissä {_b(per_day + ' päivässä')} palkkapäivään asti."
    elif loc == "sv":
        text = f"Ditt saldo är {_b(bal)}. Den här månaden: {inc} in, {out} ut."
        if sts and not recovery:
            text += f" Tryggt att använda: {_b(per_day + ' per dag')} fram till lönedagen."
    else:
        text = f"Your balance is {_b(bal)}. This month: {inc} in, {out} out."
        if sts and not recovery:
            text += f" Safe to spend: {_b(per_day + ' a day')} until payday."
    if recovery:
        sentence, tone = _recovery_sentence(rec, loc)
        return text + sentence, tone
    return text, {"critical": "concern", "comfortable": "positive"}.get(str(sts.get("status")), "neutral")


def _t_render_chart(raw: Any, payload: dict[str, Any], loc: str) -> tuple[str, str]:
    return pick(loc, "Here's the chart.", "Tässä kaavio.", "Här är diagrammet."), "neutral"


_TEMPLATES = {
    "query_spending": _t_query_spending,
    "search_transactions": _t_search_transactions,
    "get_baskets": _t_get_baskets,
    "safe_to_spend": _t_safe_to_spend,
    "recurring_payments": _t_recurring_payments,
    "spender_profile": _t_spender_profile,
    "benchmarks": _t_benchmarks,
    "simulate_what_if": _t_simulate_what_if,
    "plan_goal": _t_plan_goal,
    "create_goal": _t_create_goal,
    "update_goal": _t_create_goal,
    "list_goals": _t_list_goals,
    "survival_plan": _t_survival_plan,
    "home_readiness": _t_home_readiness,
    "explain_concept": _t_explain_concept,
    "get_overview": _t_get_overview,
    "render_chart": _t_render_chart,
}


#: tools whose positive outcome is about the user's *behaviour* (worth praising)
_PRAISE_TOOLS = {"safe_to_spend", "spender_profile", "plan_goal", "home_readiness", "get_overview", "survival_plan", "create_goal"}


def compose_answer(results: list[tuple[str, ToolResult]], persona: Persona, locale: str, *, user_text: str = "", offline_note: bool = False, recovery_context: dict[str, Any] | None = None) -> str:
    """Render a persona-styled answer from tool results (all numbers come from results)."""
    loc = norm_locale(locale)
    ok = [(n, r) for n, r in results if not r.error]
    if not ok:
        if results:
            return pick(loc, "Sorry, I couldn't fetch your data right now. Please try again in a moment.",
                        "Pahoittelut, en saanut tietojasi juuri nyt haettua. Yritä hetken päästä uudelleen.",
                        "Förlåt, jag kunde inte hämta dina uppgifter just nu. Försök igen om en stund.")
        return persona.greeting(loc)
    rec = recovery_context or next((r.raw.get("recovery") for _, r in ok if isinstance(r.raw, dict) and r.raw.get("recovery")), {})
    if rec.get("state") == "unknown":
        return _recovery_sentence(rec, loc)[0]
    recovering = rec.get("state") in ("balance_repair", "cashflow_stabilizing")
    lines: list[str] = []
    tones: list[str] = []
    for name, res in ok[:2]:
        fn = _TEMPLATES.get(name)
        if not fn:
            continue
        raw = res.raw if isinstance(res.raw, dict) else {}
        try:
            text, tone = fn(raw, res.llm_payload or {}, loc)
        except Exception:  # noqa: BLE001 - template must never break the answer
            text, tone = res.summary, "neutral"
        lines.append(text)
        tones.append(tone)
    main_tool = ok[0][0]
    variant = main_tool
    if main_tool == "query_spending":
        filters = (ok[0][1].llm_payload or {}).get("filters") or {}
        specific = filters.get("category") or filters.get("subcategory") or filters.get("basket")
        if specific and not _is_leakish(filters):
            variant = "query_spending:essential"
        elif _has("deficit", (user_text or "").lower()):
            variant = "query_spending:deficit"  # "where does the gap come from": a cost, not a streak
    if main_tool == "get_overview":
        rec = ok[0][1].raw.get("recovery") if isinstance(ok[0][1].raw, dict) else None
        if (rec or {}).get("state") in ("balance_repair", "cashflow_stabilizing"):
            variant = "get_overview:recovery"  # no daily-streak closer on a negative balance / deficit
    if main_tool == "plan_goal":
        plan = ok[0][1].raw if isinstance(ok[0][1].raw, dict) else {}
        if _f(plan.get("current_monthly_surplus")) < 0 and plan.get("feasibility") == "unrealistic":
            variant = "plan_goal:deficit"  # same condition as the honest wording in _t_plan_goal
    if main_tool == "safe_to_spend" and user_text:
        amounts = parse_amounts(user_text)
        raw = ok[0][1].raw if isinstance(ok[0][1].raw, dict) else {}
        if amounts and raw.get("safe_this_week") is not None:
            price, week = amounts[0], _f(raw.get("safe_this_week"))
            if loc == "fi":
                fit = f"{fmt_eur(price, loc)} {'mahtuu' if price <= week else 'ei mahdu'} tämän viikon turvalliseen summaan ({fmt_eur(week, loc)})."
            elif loc == "sv":
                fit = f"{fmt_eur(price, loc)} {'ryms inom' if price <= week else 'är mer än'} veckans trygga summa ({fmt_eur(week, loc)})."
            else:
                fit = f"{fmt_eur(price, loc)} {'fits within' if price <= week else 'is more than'} this week's safe amount ({fmt_eur(week, loc)})."
            lines.insert(0, fit)
            if price > week:
                tones.append("concern")
    if rec and main_tool == "query_spending" and _has("deficit", user_text.lower()):
        income, spending, surplus = (fmt_eur(rec.get(k), loc) for k in ("monthly_income", "monthly_spending", "monthly_surplus"))
        lines.append(pick(loc,
            f"Over six full months, monthly averages: income {income}, spending {spending}, net {surplus}.",
            f"Kuuden täyden kuukauden keskiarvot: tulot {income}/kk, menot {spending}/kk, erotus {surplus}/kk.",
            f"Genomsnitt över sex hela månader: inkomster {income}/mån., utgifter {spending}/mån., netto {surplus}/mån."))
    if recovering:
        variant = "query_spending:deficit" if main_tool in ("query_spending", "plan_goal") else "get_overview:recovery"
        tones = ["concern"]
        if main_tool == "simulate_what_if":
            if _f(rec.get("monthly_surplus")) < 0:
                lines.append(pick(loc, "This reduction goes towards closing the gap before saving.",
                    "Tämä vähennys auttaa kuromaan vajetta umpeen ennen säästämistä.",
                    "Minskningen hjälper till att täppa till underskottet före sparandet."))
            else:
                lines.append(pick(loc, "This reduction can help bring the negative balance towards zero before saving.",
                    "Tämä vähennys voi auttaa nostamaan miinussaldoa kohti nollaa ennen säästämistä.",
                    "Minskningen kan hjälpa det negativa saldot mot noll före sparandet."))
        if main_tool in ("safe_to_spend", "survival_plan", "list_goals", "plan_goal"):
            lines.append(pick(loc, "Secure food, housing, medicines and transport before goal transfers. If essentials do not fit, contact S-Bank customer service or free public debt advice.",
                "Turvataan ruoka, asuminen, lääkkeet ja liikkuminen ennen tavoitesiirtoja. Jos rahat eivät riitä välttämättömään, S-Pankin asiakaspalvelu tai maksuton talous- ja velkaneuvonta voi auttaa.",
                "Trygga mat, boende, mediciner och transport före målöverföringar. Om pengarna inte räcker till det nödvändiga kan S-Bankens kundtjänst eller gratis ekonomi- och skuldrådgivning hjälpa."))
    opener = persona.fallback_phrase("openers", loc)
    tone_line = ""
    if "concern" in tones:
        tone_line = persona.fallback_phrase("concern", loc)
    elif "positive" in tones and main_tool in _PRAISE_TOOLS:
        tone_line = persona.fallback_phrase("positive", loc)
    parts = [" ".join(p for p in (opener, tone_line) if p)] if (opener or tone_line) else []
    parts.append(" ".join(lines))
    closer = _CLOSERS.get(variant, {}).get(persona.id, {}).get(loc)
    if closer:
        parts.append(closer)
    concept = _CONCEPT_LINES.get(variant, {}).get(loc)
    if concept and main_tool != "explain_concept" and random.random() < 0.7:
        parts.append(concept)
    if offline_note:
        parts.append(f"_{persona.fallback_phrase('offline_note', loc)}_")
    return "\n\n".join(p for p in parts if p.strip())


async def stream_text(text: str, delay: float = 0.012) -> AsyncIterator[SSEEvent]:
    """Emit text as ``token`` events word by word (keeps the talking animation natural)."""
    for piece in re.findall(r"\S+\s*|\s+", text):
        yield ev.token(piece)
        if delay:
            await asyncio.sleep(delay)


# =============================================================================== runner


async def run_fallback(
    req: ChatRequest, ctx: ToolContext, *, message_id: str, announce: bool = True, trace: dict[str, Any] | None = None
) -> AsyncIterator[SSEEvent]:
    """Answer one chat turn without an LLM, emitting the standard SSE events.

    ``announce`` is kept for API symmetry (the orchestrator already emitted the initial
    thinking status); ``trace`` collects ``(tool, ToolResult)`` pairs for evals.
    """
    persona = get_persona(req.persona)
    loc = norm_locale(ctx.locale)
    text = req.last_user_text
    history = [m.content for m in req.messages if m.role == "user"][:-1]
    if req.image_base64:
        intent = Intent("photo", [("safe_to_spend", {})])
    else:
        intent = route(text, loc, ctx.as_of, history)
    results: list[tuple[str, ToolResult]] = trace.setdefault("results", []) if trace is not None else []
    if trace is not None:
        trace["intent"] = intent.name
    for name, args in intent.calls:
        yield ev.status("tool", status_label(name, args, loc, persona.id))
        result = await execute_tool(name, args, ctx)
        results.append((name, result))
        for widget in result.widgets:
            yield ev.widget_event(widget)
        yield ev.tool_event(name, args, result.summary)
    yield ev.status("writing", persona.text("status.writing", loc, pick(loc, "Writing…", "Kirjoitan…", "Skriver…")))
    from app.agent.orchestrator import offline_forced

    from app.agent.tools import call_analytics

    try:
        rec = await call_analytics("recovery", "recovery", ctx.customer_id)
    except Exception:  # context failure must not turn into a false green light
        rec = {"state": "unknown"}
    answer = compose_answer(results, persona, loc, user_text=text, offline_note=not offline_forced(), recovery_context=rec)
    if req.image_base64:
        prefix = pick(loc, "I can't read the photo right now — tell me the price and I'll check it exactly. ",
                      "En pysty lukemaan kuvaa juuri nyt — kerro hinta, niin lasken tarkemmin. ",
                      "Jag kan inte läsa bilden just nu — berätta priset så räknar jag exakt. ")
        answer = prefix + answer
    if intent.name == "overview" and re.fullmatch(r"\W*(hi|hello|hey|moi|hei|terve|moikka|hej|hejsan|tjena|morjens)\W*", (text or "").lower()):
        answer = persona.greeting(loc, "") + "\n\n" + answer
    async for event in stream_text(answer):
        yield event
    tools_used = [n for n, _ in results]
    yield ev.done(message_id, merge_sources(results, loc), suggest_followups(tools_used, persona.id, loc, text, results, recovery_context=rec), derive_mood(results, recovery_context=rec))
