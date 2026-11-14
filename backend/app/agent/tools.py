"""Agent tools: OpenAI JSON schemas + executors over ``app.analytics``.

Why tools (and not RAG or text-to-SQL)?
---------------------------------------
* **Correct numbers.** The model never does arithmetic over raw rows and never writes
  SQL. It chooses a tool and parameters from closed enums; deterministic, tested DuckDB
  analytics compute the figures. The prompt then forbids numbers that did not come from
  a tool, and ``evals/`` verifies that.
* **Privacy by design.** ``ToolResult.llm_payload`` is a *compact aggregate* (totals,
  top groups, a handful of rows at most). Raw transaction history and other customers'
  data never enter the prompt.
* **Generative UI.** Each executor also emits typed ``widgets`` (SPEC §5.3) — charts,
  sliders, plans — which the app renders natively inline in the chat. The model decides
  *what* to look at; the widget mapping guarantees the *visual* is always the right one
  for that data (grouped → bar/donut, over time → line, plan → goal card + button …).
* **Provenance.** ``sources`` (``tx_count`` + ``period``) powers the "Based on N
  transactions · Sep 2026" chip, so users can see what an answer rests on.
* **Writes need consent.** ``create_goal`` / ``update_goal`` only write when the user has
  explicitly confirmed in their latest message; otherwise they return an
  ``action_buttons`` proposal the user can tap.

Analytics are imported lazily by module name (``app.analytics.<module>.<function>``)
so the agent can be imported — and unit-tested with fakes — independently of DuckDB.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import math
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from typing import Any

from app.agent.settings import APP_DATA_DIR, get_settings
from app.i18n import use_locale
from app.agent.lang import norm_locale, pick
from app.agent.vocab import (
    ALL_CATEGORIES,
    ARCHETYPE_L10N,
    BASKET_LABEL,
    BASKETS,
    CATEGORY_FI_STEM,
    GROUP_BY,
    PERIODS,
    SPENDING_CATEGORIES,
    SUBCATEGORIES,
    SUBCATEGORY_LABEL,
    category_label,
    fmt_eur,
    format_period,
    normalize_category,
    parse_iso,
    resolve_period,
)

log = logging.getLogger("spankkibot.tools")

Widget = dict[str, Any]

BASKET_COLORS = {"fixed": "#5B8DEF", "irregular": "#F5A524", "leak": "#FF6B8A", "income": "#00B26F", "saving": "#3DD9B4"}
GOAL_KIND_EMOJI = {"car": "🚗", "travel": "✈️", "home": "🏡", "emergency": "🛟", "education": "🎓", "gadget": "💻", "other": "🎯"}
GOAL_KINDS = tuple(GOAL_KIND_EMOJI)


# =============================================================================== data types


@dataclass
class ToolContext:
    """Per-request context handed to every executor."""

    customer_id: str
    locale: str = "en"
    persona: str = "sisu"
    as_of: date = field(default_factory=lambda: get_settings().as_of)
    #: latest user message, used to verify explicit consent for writes
    user_text: str = ""


@dataclass
class ToolResult:
    """What a tool hands back: model view, app view, provenance."""

    llm_payload: dict[str, Any]
    widgets: list[Widget] = field(default_factory=list)
    sources: dict[str, Any] = field(default_factory=dict)  # {"tx_count": int, "period": str, "start", "end"}
    summary: str = ""
    #: raw analytics output (not sent to the model) – used for mood + fallback templates
    raw: Any = None
    error: str | None = None


class ToolError(Exception):
    """Validation problem the model can fix (returned to it as an error payload)."""


# =============================================================================== helpers


def new_widget(kind: str, data: dict[str, Any]) -> Widget:
    return {"id": f"w_{uuid.uuid4().hex[:10]}", "type": kind, "data": _jsonable(data)}


def _jsonable(obj: Any) -> Any:
    """Make analytics output JSON-safe (dates, Decimals, NaN, numpy scalars)."""

    def default(o: Any) -> Any:
        if hasattr(o, "isoformat"):
            return o.isoformat()
        if hasattr(o, "item"):
            return o.item()
        if hasattr(o, "model_dump"):
            return o.model_dump()
        return str(o)

    text = json.dumps(obj, default=default, ensure_ascii=False)
    value = json.loads(text)
    return _clean_nan(value)


def _clean_nan(v: Any) -> Any:
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else round(v, 2)
    if isinstance(v, dict):
        return {k: _clean_nan(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_clean_nan(x) for x in v]
    return v


def compact(obj: Any, max_list: int = 12, depth: int = 0) -> Any:
    """Shrink a payload for the model: round floats, cap lists, drop deep nesting."""
    if isinstance(obj, float):
        return round(obj, 2)
    if isinstance(obj, dict):
        if depth > 4:
            return "…"
        return {k: compact(v, max_list, depth + 1) for k, v in obj.items() if v not in (None, [], {})}
    if isinstance(obj, list):
        items = [compact(v, max_list, depth + 1) for v in obj[:max_list]]
        if len(obj) > max_list:
            items.append(f"+{len(obj) - max_list} more")
        return items
    return obj


def _s(ctx: "ToolContext", en: str, fi: str, sv: str) -> str:
    """Pick the summary string for the user's locale (shown in the sources chip)."""
    return pick(ctx.locale, en, fi, sv)


def _num(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
        return default if math.isnan(f) else f
    except (TypeError, ValueError):
        return default


async def call_analytics(module: str, function: str, *args: Any, **kwargs: Any) -> Any:
    """Run ``app.analytics.<module>.<function>`` in a worker thread (DuckDB is sync)."""
    mod = importlib.import_module(f"app.analytics.{module}")
    fn = getattr(mod, function)
    return await asyncio.to_thread(fn, *args, **kwargs)


def _resolve_dates(args: dict[str, Any], ctx: ToolContext, default_period: str | None = None) -> tuple[str | None, str | None]:
    """Explicit ``start``/``end`` win; otherwise a named ``period``; otherwise the default."""
    start = parse_iso(args.get("start"))
    end = parse_iso(args.get("end"))
    if not start and not end:
        period = args.get("period") or default_period
        if period:
            start, end = resolve_period(period, ctx.as_of)
    if end and end > ctx.as_of:
        end = ctx.as_of
    if start and end and start > end:
        start, end = end, start
    return (start.isoformat() if start else None, end.isoformat() if end else None)


async def _count_tx(ctx: ToolContext, start: str | None, end: str | None) -> int:
    """Number of transactions an analysis window rests on (for the sources chip)."""
    try:
        res = await call_analytics("query", "query_spending", ctx.customer_id, start=start, end=end, direction="all")
        return int(_num((res or {}).get("count")))
    except Exception:  # noqa: BLE001 - provenance is best-effort
        return 0


def _sources(ctx: ToolContext, tx_count: int, start: Any, end: Any) -> dict[str, Any]:
    s, e = parse_iso(start), parse_iso(end)
    return {
        "tx_count": int(tx_count or 0),
        "period": format_period(s, e, ctx.locale),
        "start": s.isoformat() if s else None,
        "end": e.isoformat() if e else None,
    }


def _window_months(ctx: ToolContext, months: int) -> tuple[str, str]:
    start, end = resolve_period(f"last_{months}_months" if months in (3, 6, 12) else "last_3_months", ctx.as_of)
    assert start and end
    return start.isoformat(), end.isoformat()


def user_confirmed(text: str) -> bool:
    """Did the user explicitly ask for / agree to a write in their latest message?"""
    low = (text or "").lower()
    patterns = (
        r"\b(yes|yeah|yep|sure|ok|okay|confirm|confirmed|do it|go ahead|please do|sounds good|let'?s do it)\b",
        r"\b(create|add|save|set up|make|start|update|change|edit)\b.{0,40}\bgoal\b",
        r"\b(kyllä|joo|juu|jep|selvä|ok|vahvistan|tehdään|tee se|luo|lisää|tallenna|päivitä|muuta)\b",
        # Swedish: "spara" alone means "save money", so only explicit goal verbs count
        r"\b(skapa|lägg till|lägga till|uppdatera|ändra)\b.{0,40}\b(spar)?mål",
    )
    if any(re.search(p, low) for p in patterns):
        return True
    # Swedish "ja" is Finnish "and": only read it as consent in a Swedish message
    from app.agent.lang import detect_language

    return detect_language(low, "en") == "sv" and re.search(r"\b(ja|japp|visst|okej|bekräftar|gör det|kör på)\b", low) is not None


def guess_goal_kind(name: str | None) -> str:
    low = (name or "").lower()
    if re.search(r"\b(el)?bil(en|ar|arna)?\b", low):  # Swedish "bil" (not "mobil")
        return "car"
    table = (
        ("car", ("car", "auto", "vehicle", "moped", "mopo")),
        ("travel", ("travel", "trip", "holiday", "vacation", "matka", "loma", "reissu", "resa", "resor", "semester")),
        ("home", ("home", "house", "apartment", "flat", "asunto", "koti", "talo", "down payment", "käsiraha",
                  "bostad", "lägenhet", "egnahemshus", "insats")),
        ("emergency", ("emergency", "buffer", "rainy", "puskuri", "hätä", "pahan päivän", "buffert", "nödfond")),
        ("education", ("study", "school", "course", "education", "opiskelu", "koulu", "kurssi", "studier", "skola",
                       "utbildning")),
        ("gadget", ("laptop", "phone", "computer", "console", "bike", "läppäri", "puhelin", "tietokone", "pyörä",
                    "dator", "telefon", "mobil", "konsol", "cykel")),
    )
    for kind, words in table:
        if any(w in low for w in words):
            return kind
    return "other"


# =============================================================================== schemas

_PERIOD_DESC = (
    "Named period relative to today (preferred over start/end — avoids date mistakes). "
    "'last_month' = previous calendar month; 'this_month' = month to date."
)
_DATE_DESC = "ISO date YYYY-MM-DD (inclusive). Only use when the user names specific dates."


def _fn(name: str, description: str, properties: dict[str, Any] | None = None, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties or {},
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


_FILTERS: dict[str, Any] = {
    "period": {"type": "string", "enum": list(PERIODS), "description": _PERIOD_DESC},
    "start": {"type": "string", "description": _DATE_DESC},
    "end": {"type": "string", "description": _DATE_DESC},
    "category": {"type": "string", "enum": list(ALL_CATEGORIES), "description": "Dataset category. 'Restaurants' covers dining out, cafés, fast food and bars."},
    "subcategory": {
        "type": "string",
        "enum": list(SUBCATEGORIES),
        "description": "Narrower merchant type within a category, e.g. 'taxi' (Transportation), 'fast_food_cafes' (Restaurants), 'convenience_store' (Groceries). Use for questions like 'taxis' or 'coffee'.",
    },
    "basket": {
        "type": "string",
        "enum": list(BASKETS),
        "description": "Three-baskets model: fixed = mandatory & regular (rent, utilities, groceries, transit, subscriptions); irregular = mandatory but irregular (health, repairs, car); leak = everyday discretionary spending (eating out, taxis, entertainment, shopping, travel). income/saving are non-spending flows.",
    },
    "merchant": {"type": "string", "description": "Merchant id like 'MRC-RES-0038' (only if previously returned by a tool)."},
}

TOOL_SCHEMAS: list[dict[str, Any]] = [
    _fn("get_overview", "Snapshot of the user's finances today: balance, this month's income/spent/saved, spending by basket, safe-to-spend, goals. Use for 'how am I doing?' style questions."),
    _fn(
        "query_spending",
        "The MyData engine: sums the user's transactions with flexible filters and grouping. Use for any 'how much did I spend on X (in period Y)?' question, comparisons and trends. group_by='month' for trends over time, 'category' or 'basket' for a split, 'merchant' for top places, 'weekday'/'hour' for habits.",
        {
            **_FILTERS,
            "group_by": {"type": "string", "enum": list(GROUP_BY), "description": "How to split the total. 'none' returns just the total."},
            "direction": {"type": "string", "enum": ["out", "in"], "description": "'out' = spending (default), 'in' = income."},
            "top_n": {"type": "integer", "minimum": 1, "maximum": 30, "description": "Max groups to return (default 12)."},
        },
    ),
    _fn(
        "search_transactions",
        "List individual transactions matching filters (newest first). Use when the user wants to see specific purchases, the biggest purchases, or find something.",
        {
            **_FILTERS,
            "min_amount": {"type": "number", "description": "Minimum absolute amount in EUR."},
            "max_amount": {"type": "number", "description": "Maximum absolute amount in EUR."},
            "text": {"type": "string", "description": "Free-text match on merchant/category label."},
            "sort": {"type": "string", "enum": ["newest", "largest"], "description": "'largest' to find the biggest purchases."},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Max rows (default 10)."},
        },
    ),
    _fn(
        "get_baskets",
        "Monthly split of spending into the three baskets (fixed / irregular / leak) plus income and saving, with the top items per basket this month and plain-language explanations. Use to teach the three-baskets model with the user's own numbers.",
        {"months": {"type": "integer", "minimum": 1, "maximum": 12, "description": "How many recent months (default 6)."}},
    ),
    _fn("safe_to_spend", "How much the user can safely spend today / this week until next payday, after upcoming bills, an irregular-costs buffer and goal contributions. Use for 'can I afford…', 'what is safe to spend', or photos of price tags."),
    _fn("recurring_payments", "Detected recurring payments and subscriptions (label, average amount, cadence, basket) and their monthly total."),
    _fn("spender_profile", "The user's spender archetype (e.g. weekend treater, latte leaker, steady planner) with trait scores: savings rate, leak share, weekend share, small purchases per week, late-night share, volatility. Use for 'what kind of spender am I?'."),
    _fn("benchmarks", "Compare the user's monthly spending per category, income and savings rate with peers of the same age group in the dataset and with Statistics Finland household averages."),
    _fn(
        "simulate_what_if",
        "Simulate cutting (or increasing) spending: e.g. 'reduce dining out by 20 %' → monthly and cumulative savings over the horizon, optionally with an investment return. Each adjustment targets a category OR a basket.",
        {
            "adjustments": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string", "enum": list(SPENDING_CATEGORIES)},
                        "basket": {"type": "string", "enum": ["fixed", "irregular", "leak"]},
                        "change_pct": {"type": "number", "description": "Percent change, negative = cut (e.g. -20)."},
                    },
                    "required": ["change_pct"],
                },
            },
            "horizon_months": {"type": "integer", "minimum": 1, "maximum": 120, "description": "Default 12."},
            "invest_return_pct": {"type": "number", "description": "Optional yearly return % if the savings are invested (general illustration only, default 0)."},
        },
        ["adjustments"],
    ),
    _fn("list_goals", "The user's saved savings goals with progress."),
    _fn(
        "plan_goal",
        "Plan a savings goal: monthly amount needed, feasibility vs the user's current surplus, and concrete cuts (mostly from leaks) to close the gap. Use for 'help me save for X'. Does NOT save the goal — the app shows a 'Create goal' button.",
        {
            "target_amount": {"type": "number", "description": "Goal amount in EUR."},
            "deadline": {"type": "string", "description": "ISO date YYYY-MM-DD or YYYY-MM. Omit to let the planner suggest one."},
            "name": {"type": "string", "description": "Short goal name, e.g. 'Car'."},
            "saved_amount": {"type": "number", "description": "Already saved towards it (EUR)."},
        },
        ["target_amount"],
    ),
    _fn(
        "create_goal",
        "Save a new goal. ONLY call when the user explicitly asked to create/save it or said yes to your proposal; otherwise use plan_goal. Reuse exactly the name, amount and deadline of the plan the user agreed to (omit deadline if none was stated).",
        {
            "name": {"type": "string"},
            "target_amount": {"type": "number"},
            "deadline": {"type": "string", "description": "ISO date or YYYY-MM"},
            "emoji": {"type": "string"},
            "kind": {"type": "string", "enum": list(GOAL_KINDS)},
            "saved_amount": {"type": "number"},
        },
        ["name", "target_amount"],
    ),
    _fn(
        "update_goal",
        "Change an existing goal (amount, deadline, saved amount, name). ONLY when the user explicitly asked for that change.",
        {
            "goal_id": {"type": "string", "description": "Id from list_goals."},
            "name": {"type": "string"},
            "target_amount": {"type": "number"},
            "saved_amount": {"type": "number"},
            "deadline": {"type": "string"},
            "monthly_contribution": {"type": "number"},
        },
        ["goal_id"],
    ),
    _fn(
        "survival_plan",
        "Plan how to get to the next payday (or a date) with a given amount of money: bills still due, free money per day/week, category budgets and tips. Use for 'how do I survive this month with 300 €?'.",
        {
            "amount": {"type": "number", "description": "Money available in EUR (default: current balance)."},
            "until": {"type": "string", "description": "ISO end date (default: next payday)."},
        },
    ),
    _fn(
        "home_readiness",
        "Mortgage readiness check using the bank's anonymised mortgage dataset: loan and equity needed, required income vs the user's, verdict and gaps.",
        {"property_price": {"type": "number", "description": "Home price in EUR (optional)."}},
    ),
    _fn(
        "explain_concept",
        "Show a short Money Gym micro-lesson card (with a quiz) on a financial concept. Use when the user asks what something means, or to add a teaching moment. Topics include: three_baskets, emergency_fund, compound_interest, pay_yourself_first, safe_to_spend, budgeting_50_30_20, inflation, subscriptions, investing_basics, mortgage_basics, impulse_spending.",
        {"topic": {"type": "string", "description": "Concept id or short phrase, e.g. 'compound_interest'."}},
        ["topic"],
    ),
    _fn(
        "render_chart",
        "Draw a chart from numbers you ALREADY got from another tool in this conversation (never invent data). Use only when no other tool already produced the right chart.",
        {
            "title": {"type": "string"},
            "chart_type": {"type": "string", "enum": ["bar", "line", "donut"]},
            "unit": {"type": "string", "enum": ["€", "%", ""]},
            "data": {
                "type": "array",
                "maxItems": 24,
                "items": {
                    "type": "object",
                    "properties": {"label": {"type": "string"}, "value": {"type": "number"}},
                    "required": ["label", "value"],
                },
            },
        },
        ["title", "chart_type", "data"],
    ),
]

TOOL_NAMES: tuple[str, ...] = tuple(t["function"]["name"] for t in TOOL_SCHEMAS)


# =============================================================================== status labels

_STATUS: dict[str, dict[str, dict[str, str]]] = {
    # tool → persona ("*" = shared) → locale → label template
    "get_overview": {"*": {"en": "Opening your money snapshot…", "fi": "Avaan rahatilanteesi…", "sv": "Öppnar din ekonomiska översikt…"}},
    "query_spending": {
        "*": {"en": "Checking your {what} spending…", "fi": "Tarkistan {what_fi}kulujasi…", "sv": "Kollar dina utgifter: {what_sv}…"},
    },
    "search_transactions": {"*": {"en": "Looking through your {what} transactions…", "fi": "Selaan {what_fi}tapahtumiasi…", "sv": "Går igenom dina transaktioner: {what_sv}…"}},
    "get_baskets": {
        "sisu": {"en": "Weighing your three baskets…", "fi": "Punnitsen kolmea koriasi…", "sv": "Väger dina tre korgar…"},
        "aava": {"en": "Sorting your spending into the three baskets…", "fi": "Lajittelen kulusi kolmeen koriin…", "sv": "Sorterar dina utgifter i de tre korgarna…"},
    },
    "safe_to_spend": {
        "sisu": {"en": "Calculating your safe zone until payday…", "fi": "Lasken turva-alueesi palkkapäivään asti…", "sv": "Räknar ut din trygga zon fram till lönedagen…"},
        "aava": {"en": "Working out what is safe to spend…", "fi": "Lasken, paljonko voit turvallisesti käyttää…", "sv": "Räknar ut hur mycket du tryggt kan använda…"},
    },
    "recurring_payments": {"*": {"en": "Finding your recurring payments…", "fi": "Etsin toistuvia maksujasi…", "sv": "Letar fram dina återkommande betalningar…"}},
    "spender_profile": {
        "sisu": {"en": "Running your spender fitness test…", "fi": "Teen kuluttajan kuntotestiä…", "sv": "Gör ett konditionstest av din konsumtion…"},
        "aava": {"en": "Reading your spending habits…", "fi": "Tutkin kulutustottumuksiasi…", "sv": "Läser av dina konsumtionsvanor…"},
    },
    "benchmarks": {"*": {"en": "Comparing you with people your age…", "fi": "Vertaan sinua ikätovereihisi…", "sv": "Jämför dig med jämnåriga…"}},
    "simulate_what_if": {
        "sisu": {"en": "Simulating the gains from your cut…", "fi": "Simuloin säästöhyötyjä…", "sv": "Simulerar vinsten av din nedskärning…"},
        "aava": {"en": "Simulating what that change would mean…", "fi": "Simuloin, mitä muutos tarkoittaisi…", "sv": "Simulerar vad förändringen skulle betyda…"},
    },
    "list_goals": {"*": {"en": "Checking your goals…", "fi": "Tarkistan tavoitteesi…", "sv": "Kollar dina sparmål…"}},
    "plan_goal": {
        "sisu": {"en": "Building your training plan for {what}…", "fi": "Rakennan treeniohjelmaa: {what}…", "sv": "Bygger ditt träningsprogram: {what}…"},
        "aava": {"en": "Planning your path to {what}…", "fi": "Suunnittelen polkua kohti tavoitetta: {what}…", "sv": "Planerar vägen till ditt mål: {what}…"},
    },
    "create_goal": {"*": {"en": "Saving your goal…", "fi": "Tallennan tavoitteesi…", "sv": "Sparar ditt mål…"}},
    "update_goal": {"*": {"en": "Updating your goal…", "fi": "Päivitän tavoitettasi…", "sv": "Uppdaterar ditt mål…"}},
    "survival_plan": {
        "sisu": {"en": "Drawing up your survival game plan…", "fi": "Laadin selviytymissuunnitelmaa…", "sv": "Gör upp din matchplan för månaden…"},
        "aava": {"en": "Planning how to make it to payday…", "fi": "Suunnittelen, miten pärjäät palkkapäivään…", "sv": "Planerar hur du klarar dig till lönedagen…"},
    },
    "home_readiness": {"*": {"en": "Checking your home-loan readiness…", "fi": "Tarkistan asuntolainavalmiuttasi…", "sv": "Kollar hur redo du är för ett bostadslån…"}},
    "explain_concept": {"*": {"en": "Fetching a Money Gym lesson…", "fi": "Haen Rahasalin oppitunnin…", "sv": "Hämtar en lektion från Pengagymmet…"}},
    "render_chart": {"*": {"en": "Drawing your chart…", "fi": "Piirrän kaavion…", "sv": "Ritar ditt diagram…"}},
}


_CATEGORY_EN_STEM = {
    "Groceries": "grocery", "Restaurants": "restaurant", "Transportation": "transport", "Utilities": "utility",
    "Entertainment": "entertainment", "Health": "health", "Home & Tech": "home & tech", "Housing": "housing",
    "Lifestyle": "shopping", "Travel": "travel", "Salary": "salary", "Other Income": "income",
    "Invest Deposit": "investment", "Salary Sweep": "savings", "Invest Withdraw": "investment",
}
_BASKET_STEM = {
    "fixed": ("fixed-cost", "kiinteiden menojen "), "irregular": ("irregular", "epäsäännöllisiä "),
    "leak": ("leak", "vuoto"), "income": ("income", "tulo"), "saving": ("saving", "säästö"),
}
_BASKET_SV = {"fixed": "fasta måsten", "irregular": "oregelbundna måsten", "leak": "vardagsläckor",
              "income": "inkomster", "saving": "sparande"}


def status_label(name: str, args: dict[str, Any], locale: str = "en", persona: str = "sisu") -> str:
    """Friendly, persona- and locale-aware status line for a tool call.

    e.g. ``query_spending(category=Restaurants)`` → "Checking your restaurant spending…" /
    "Tarkistan ravintolakulujasi…".
    """
    table = _STATUS.get(name, {})
    loc = norm_locale(locale)
    template = (table.get(persona) or table.get("*") or {}).get(loc)
    if not template:
        return pick(loc, "Working on it…", "Työstän…", "Jobbar på det…")
    what, what_fi, what_sv = "", "", ""
    sub = args.get("subcategory")
    cat = normalize_category(args.get("category"))
    basket = args.get("basket")
    if sub in SUBCATEGORY_LABEL:
        what, what_fi, what_sv = SUBCATEGORY_LABEL[sub]["en"], SUBCATEGORY_LABEL[sub]["fi"], SUBCATEGORY_LABEL[sub]["sv"]
    elif cat:
        what, what_fi, what_sv = _CATEGORY_EN_STEM.get(cat, cat.lower()), CATEGORY_FI_STEM.get(cat, ""), category_label(cat, "sv")
    elif basket in _BASKET_STEM:
        (what, what_fi), what_sv = _BASKET_STEM[basket], _BASKET_SV[basket]
    if name == "plan_goal":
        amount = _num(args.get("target_amount"))
        what = str(args.get("name") or (fmt_eur(amount, loc) if amount else pick(loc, "your goal", "tavoite", "ditt mål")))
        what_fi = what_sv = what
    if loc == "sv" and not what_sv:
        template = {"query_spending": "Kollar dina utgifter…", "search_transactions": "Går igenom dina transaktioner…"}.get(name, template)
    label = template.format(what=what, what_fi=what_fi, what_sv=what_sv)
    return re.sub(r"\s{2,}", " ", label)


# =============================================================================== executors

Executor = Callable[[dict[str, Any], ToolContext], Awaitable[ToolResult]]


async def _get_overview(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    ov = _jsonable(await call_analytics("overview", "get_overview", ctx.customer_id))
    month = ov.get("month") or {}
    sts = ov.get("safe_to_spend") or {}
    goals = ov.get("goals") or []
    rec = ov.get("recovery") or {}
    payload = {
        "as_of": ov.get("as_of"),
        "balance": ov.get("balance"),
        "this_month": month,
        "safe_to_spend": {k: sts.get(k) for k in ("safe_total", "safe_per_day", "safe_this_week", "days_until_payday", "next_payday", "status")},
        "recovery": {k: rec.get(k) for k in ("state", "months", "balance", "monthly_income", "monthly_spending", "monthly_surplus", "deficit", "goal_monthly_need", "planned_monthly_change", "urgency", "goal_contributions", "goal_reservations_present", "tx_count")} if rec else None,
        "goals": [{k: g.get(k) for k in ("id", "name", "target_amount", "saved_amount", "deadline", "progress")} for g in goals],
        "nudges": [n.get("text") for n in (ov.get("nudges") or [])][:3],
    }
    loc = ctx.locale
    items = [
        {"label": pick(loc, "Balance", "Saldo", "Saldo"), "value": _num(ov.get("balance")), "unit": "€", "tone": "neutral"},
        {"label": pick(loc, "Income (month)", "Tulot (kk)", "Inkomster (mån.)"), "value": _num(month.get("income")), "unit": "€", "tone": "good"},
        {"label": pick(loc, "Spent (month)", "Kulut (kk)", "Utgifter (mån.)"), "value": _num(month.get("spent")), "unit": "€", "tone": "neutral"},
        {"label": pick(loc, "Saved (month)", "Säästetty (kk)", "Sparat (mån.)"), "value": _num(month.get("saved")), "unit": "€", "tone": "good"},
    ]
    start, end = resolve_period("this_month", ctx.as_of)
    count = await _count_tx(ctx, start.isoformat() if start else None, end.isoformat() if end else None)
    widgets = [new_widget("kpi", {"items": items})]
    by_basket = month.get("by_basket") or {}
    if by_basket:
        widgets.append(new_widget("donut_chart", _basket_donut(by_basket, loc)))
    return ToolResult(payload, widgets, _sources(ctx, count, start, end), _s(ctx, f"Balance {fmt_eur(_num(ov.get('balance')))}", f"Saldo {fmt_eur(_num(ov.get('balance')), 'fi')}", f"Saldo {fmt_eur(_num(ov.get('balance')), 'sv')}"), ov)


def _basket_donut(by_basket: dict[str, Any], loc: str) -> dict[str, Any]:
    return {
        "title": pick(loc, "This month's baskets", "Tämän kuun korit", "Månadens korgar"),
        "unit": "€",
        "slices": [
            {"label": BASKET_LABEL[b][loc], "value": _num(by_basket.get(b)), "color": BASKET_COLORS[b]}
            for b in ("fixed", "irregular", "leak")
        ],
    }


async def _query_spending(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    start, end = _resolve_dates(args, ctx, default_period="this_month")
    category = normalize_category(args.get("category"))
    sub = args.get("subcategory") if args.get("subcategory") in SUBCATEGORIES else None
    mcc: Any = None
    if sub:
        parent, codes = SUBCATEGORIES[sub]
        category = category or parent
        mcc = codes[0] if len(codes) == 1 else list(codes)
    group_by = args.get("group_by") if args.get("group_by") in GROUP_BY else "none"
    direction = args.get("direction") if args.get("direction") in ("in", "out") else "out"
    top_n = max(1, min(int(_num(args.get("top_n"), 12)), 30))
    basket = args.get("basket") if args.get("basket") in BASKETS else None
    kwargs = dict(start=start, end=end, category=category, basket=basket, merchant=args.get("merchant"), group_by=group_by, direction=direction, top_n=top_n)
    res = await _query_with_mcc(ctx, mcc, kwargs)
    total, count = _num(res.get("total")), int(_num(res.get("count")))
    period = res.get("period") or {"start": start, "end": end}
    p_start, p_end = period.get("start") or start, period.get("end") or end
    loc = ctx.locale
    what = (SUBCATEGORY_LABEL[sub][loc] if sub else category_label(category, loc)) or (BASKET_LABEL[basket][loc] if basket else pick(loc, "all", "kaikki", "allt"))
    groups = res.get("groups") or []
    payload: dict[str, Any] = {
        "what": what,
        "filters": {k: v for k, v in {"category": category, "subcategory": sub, "basket": basket, "direction": direction}.items() if v},
        "period": {"start": p_start, "end": p_end, "label": format_period(p_start, p_end, loc)},
        "total": round(total, 2),
        "count": count,
        "avg_tx": round(_num(res.get("avg_tx")), 2),
    }
    if group_by != "none":
        payload["group_by"] = group_by
        payload["groups"] = [{"label": g.get("label") or g.get("key"), "total": round(_num(g.get("total")), 2), "count": g.get("count")} for g in groups[:top_n]]
    widgets = _spending_widgets(group_by, groups, payload, ctx)
    summary = f"{what} · {payload['period']['label']}: {fmt_eur(total, loc)} ({count} {pick(loc, 'tx', 'tap.', 'st.')})"
    return ToolResult(payload, widgets, _sources(ctx, count, p_start, p_end), summary, res)


async def _query_with_mcc(ctx: ToolContext, mcc: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Call query_spending. The engine filters on a single MCC, so a sub-category that
    spans several MCCs (e.g. fuel = 5541 + 5542) is queried per code and merged
    (totals and counts add up; groups merge by key)."""
    if not isinstance(mcc, list):
        return _jsonable(await call_analytics("query", "query_spending", ctx.customer_id, mcc=mcc, **kwargs))
    parts = await asyncio.gather(*(call_analytics("query", "query_spending", ctx.customer_id, mcc=m, **kwargs) for m in mcc))
    parts = [_jsonable(p) for p in parts]
    merged: dict[str, Any] = {"total": 0.0, "count": 0, "groups": [], "period": parts[0].get("period") if parts else {}}
    groups: dict[str, dict[str, Any]] = {}
    for p in parts:
        merged["total"] += _num(p.get("total"))
        merged["count"] += int(_num(p.get("count")))
        for g in p.get("groups") or []:
            key = str(g.get("key"))
            agg = groups.setdefault(key, {"key": key, "label": g.get("label") or key, "total": 0.0, "count": 0})
            agg["total"] += _num(g.get("total"))
            agg["count"] += int(_num(g.get("count")))
    chrono = kwargs.get("group_by") in ("month", "week", "day", "hour", "weekday")
    merged["groups"] = sorted(groups.values(), key=(lambda g: g["key"]) if chrono else (lambda g: -abs(g["total"])))
    merged["avg_tx"] = merged["total"] / merged["count"] if merged["count"] else 0.0
    return merged


def _spending_widgets(group_by: str, groups: list[dict[str, Any]], payload: dict[str, Any], ctx: ToolContext) -> list[Widget]:
    loc = ctx.locale
    title_what = payload["what"].capitalize()
    period_label = payload["period"]["label"]
    if group_by == "none" or not groups:
        items = [
            {"label": f"{title_what} · {period_label}", "value": payload["total"], "unit": "€", "tone": "neutral"},
            {"label": pick(loc, "Transactions", "Tapahtumia", "Transaktioner"), "value": payload["count"], "unit": "", "tone": "neutral"},
            {"label": pick(loc, "Average", "Keskiostos", "Medelköp"), "value": payload["avg_tx"], "unit": "€", "tone": "neutral"},
        ]
        return [new_widget("kpi", {"items": items})]
    if group_by in ("month", "week", "day"):
        points = [{"x": str(g.get("key") or g.get("label")), "y": round(_num(g.get("total")), 2)} for g in groups]
        points.sort(key=lambda p: p["x"])
        return [new_widget("line_chart", {"title": f"{title_what} · {period_label}", "unit": "€", "points": points})]
    labels = [(str(g.get("label") or g.get("key")), round(abs(_num(g.get("total"))), 2), str(g.get("key"))) for g in groups]
    if group_by in ("category", "basket") and 1 < len(labels) <= 6:
        slices = [
            {"label": BASKET_LABEL.get(key, {}).get(loc, label) if group_by == "basket" else label, "value": value, **({"color": BASKET_COLORS[key]} if key in BASKET_COLORS else {})}
            for label, value, key in labels
        ]
        return [new_widget("donut_chart", {"title": f"{title_what} · {period_label}", "unit": "€", "slices": slices})]
    top = max((v for _, v, _ in labels), default=0)
    if group_by in ("weekday", "hour"):
        bars = [{"label": label, "value": value, "highlight": value == top} for label, value, _ in labels]
    else:
        bars = [{"label": label, "value": value, "highlight": i == 0} for i, (label, value, _) in enumerate(labels)]
    return [new_widget("bar_chart", {"title": f"{title_what} · {period_label}", "unit": "€", "bars": bars})]


async def _search_transactions(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    start, end = _resolve_dates(args, ctx, default_period=None)
    category = normalize_category(args.get("category"))
    sub = args.get("subcategory") if args.get("subcategory") in SUBCATEGORIES else None
    if sub:
        category = category or SUBCATEGORIES[sub][0]
    limit = max(1, min(int(_num(args.get("limit"), 10)), 20))
    sort_largest = args.get("sort") == "largest"
    fetch = 200 if (sort_largest or sub) else limit
    basket = args.get("basket") if args.get("basket") in BASKETS else None
    res = _jsonable(
        await call_analytics(
            "query",
            "search_transactions",
            ctx.customer_id,
            start=start,
            end=end,
            category=category,
            basket=basket,
            merchant=args.get("merchant"),
            min_amount=args.get("min_amount"),
            max_amount=args.get("max_amount"),
            text=args.get("text"),
            limit=fetch,
            offset=0,
        )
    )
    items: list[dict[str, Any]] = res.get("items") or []
    total_count = int(_num(res.get("total_count"), len(items)))
    if sub:
        codes = set(SUBCATEGORIES[sub][1])
        items = [t for t in items if t.get("mcc") is not None and int(_num(t.get("mcc"))) in codes]
        total_count = len(items) if len(items) < fetch else total_count
    if sort_largest:
        if not basket and not category:
            # "biggest purchases" = spending, not salary or transfers to savings
            items = [t for t in items if _num(t.get("amount")) < 0 and t.get("basket") not in ("income", "saving")]
        items = sorted(items, key=lambda t: _num(t.get("amount")))  # most negative first
    shown = items[:limit]
    total = round(sum(_num(t.get("amount")) for t in shown), 2)
    loc = ctx.locale
    what = SUBCATEGORY_LABEL[sub][loc] if sub else (category_label(category, loc) or pick(loc, "transactions", "tapahtumat", "transaktioner"))
    title = pick(loc, f"Largest {what}", f"Suurimmat: {what}", f"Största: {what}") if sort_largest else what.capitalize()
    payload = {
        "what": what,
        "total_count": total_count,
        "shown": len(shown),
        "shown_total": total,
        "items": [
            {"date": t.get("date"), "amount": t.get("amount"), "label": t.get("merchant_label") or t.get("category"), "category": t.get("category"), "basket": t.get("basket")}
            for t in shown[:10]
        ],
    }
    dates = [t.get("date") for t in shown if t.get("date")]
    p_start = start or (min(dates) if dates else None)
    p_end = end or (max(dates) if dates else None)
    widgets = [new_widget("transaction_list", {"title": title, "items": shown, "total": total})]
    return ToolResult(payload, widgets, _sources(ctx, total_count, p_start, p_end), f"{len(shown)} {what}", res)


async def _get_baskets(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    months = max(1, min(int(_num(args.get("months"), 6)), 12))
    res = _jsonable(await call_analytics("baskets", "get_baskets", ctx.customer_id, months=months))
    cur = res.get("current_month") or {}
    explanations = res.get("explanations") or {}
    month_rows = res.get("months") or []
    spend = sum(_num(cur.get(b)) for b in ("fixed", "irregular", "leak")) or 1.0
    payload = {
        "current_month": {b: cur.get(b) for b in ("month", "fixed", "irregular", "leak", "income", "saving")},
        "shares_pct": {b: round(100 * abs(_num(cur.get(b))) / abs(spend), 1) for b in ("fixed", "irregular", "leak")},
        "top": {b: (cur.get("top") or {}).get(b, [])[:3] for b in ("fixed", "irregular", "leak")},
        "months": [{k: m.get(k) for k in ("month", "fixed", "irregular", "leak", "income", "saving")} for m in month_rows][-months:],
        "explanations": explanations,
    }
    month_label = cur.get("month") or (month_rows[-1].get("month") if month_rows else ctx.as_of.strftime("%Y-%m"))
    widget = new_widget(
        "basket_breakdown",
        {
            "month": month_label,
            "fixed": _num(cur.get("fixed")),
            "irregular": _num(cur.get("irregular")),
            "leak": _num(cur.get("leak")),
            "explanations": explanations,
            "top": cur.get("top") or {"fixed": [], "irregular": [], "leak": []},
        },
    )
    widgets = [widget]
    if len(month_rows) >= 3:
        widgets.append(
            new_widget(
                "line_chart",
                {
                    "title": pick(ctx.locale, "Leaks per month", "Vuodot kuukausittain", "Läckor per månad"),
                    "unit": "€",
                    "points": [{"x": str(m.get("month")), "y": round(abs(_num(m.get("leak"))), 2)} for m in month_rows],
                },
            )
        )
    start, end = _window_months(ctx, months if months in (3, 6, 12) else 6)
    if month_rows:
        start = f"{month_rows[0].get('month')}-01" if month_rows[0].get("month") else start
    count = await _count_tx(ctx, start, end)
    return ToolResult(payload, widgets, _sources(ctx, count, start, end), _s(ctx, f"Baskets · {month_label}", f"Korit · {month_label}", f"Korgar · {month_label}"), res)


async def _safe_to_spend(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    res = _jsonable(await call_analytics("safe_to_spend", "safe_to_spend", ctx.customer_id))
    payload = compact({k: res.get(k) for k in ("balance", "next_payday", "days_until_payday", "upcoming_bills", "irregular_buffer", "goal_contributions", "safe_total", "safe_per_day", "safe_this_week", "status", "explanation")}, max_list=6)
    start, end = _window_months(ctx, 3)
    count = await _count_tx(ctx, start, end)
    summary = _s(ctx, f"Safe today {fmt_eur(_num(res.get('safe_per_day')))} · {res.get('status')}", f"Turvallisesti tänään {fmt_eur(_num(res.get('safe_per_day')), 'fi')}", f"Tryggt i dag {fmt_eur(_num(res.get('safe_per_day')), 'sv')}")
    return ToolResult(payload, [new_widget("safe_to_spend", res)], _sources(ctx, count, start, end), summary, res)


async def _recurring_payments(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    res = _jsonable(await call_analytics("recurring", "recurring_payments", ctx.customer_id))
    items = res.get("items") or []
    payload = {
        "monthly_total": res.get("monthly_total"),
        "count": len(items),
        "items": [{k: i.get(k) for k in ("label", "category", "avg_amount", "cadence", "day_of_month", "basket")} for i in items[:12]],
    }
    loc = ctx.locale
    bars = [{"label": str(i.get("label")), "value": round(abs(_num(i.get("avg_amount"))), 2), "highlight": n == 0} for n, i in enumerate(sorted(items, key=lambda i: -abs(_num(i.get("avg_amount")))))][:12]
    widgets = [
        new_widget("kpi", {"items": [{"label": pick(loc, "Recurring / month", "Toistuvat / kk", "Återkommande / mån."), "value": abs(_num(res.get("monthly_total"))), "unit": "€", "tone": "neutral"}, {"label": pick(loc, "Payments", "Maksuja", "Betalningar"), "value": len(items), "unit": "", "tone": "neutral"}]}),
    ]
    if bars:
        widgets.append(new_widget("bar_chart", {"title": pick(loc, "Recurring payments", "Toistuvat maksut", "Återkommande betalningar"), "unit": "€", "bars": bars}))
    start, end = _window_months(ctx, 6)
    count = await _count_tx(ctx, start, end)
    return ToolResult(payload, widgets, _sources(ctx, count, start, end), _s(ctx, f"{len(items)} recurring", f"{len(items)} toistuvaa", f"{len(items)} återkommande"), res)


async def _spender_profile(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    res = _jsonable(await call_analytics("profile", "spender_profile", ctx.customer_id))
    payload = compact(res, max_list=8)
    key = (res.get("archetype") or {}).get("key")
    table = ARCHETYPE_L10N.get(ctx.locale, {})
    if key in table:  # the REST layer localises too; keep the model's view unambiguous
        payload[f"archetype_{ctx.locale}"] = {"name": table[key][0], "description": table[key][1]}
    start, end = _window_months(ctx, 6)
    count = await _count_tx(ctx, start, end)
    arch = (res.get("archetype") or {}).get("name", "")
    return ToolResult(payload, [new_widget("spender_profile", res)], _sources(ctx, count, start, end), _s(ctx, f"Archetype: {arch}", f"Tyyppi: {arch}", f"Typ: {arch}"), res)


async def _benchmarks(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    res = _jsonable(await call_analytics("benchmarks", "benchmarks", ctx.customer_id))
    cats = sorted(res.get("categories") or [], key=lambda c: -abs(_num(c.get("you_monthly"))))
    subset = {
        "peer_group": res.get("peer_group"),
        "categories": cats[:8],
        "income": res.get("income"),
        "savings_rate": res.get("savings_rate"),
        "sources": res.get("sources"),
    }
    payload = compact({**subset, "sources": [s.get("name") for s in (res.get("sources") or []) if isinstance(s, dict)]}, max_list=8)
    start, end = _window_months(ctx, 12)
    count = await _count_tx(ctx, start, end)
    return ToolResult(payload, [new_widget("benchmark", subset)], _sources(ctx, count, start, end), _s(ctx, f"vs {(res.get('peer_group') or {}).get('label', 'peers')}", "Vertailu ikätovereihin", "Jämförelse med jämnåriga"), res)


def _clean_adjustments(raw: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        change = _num(item.get("change_pct"), float("nan"))
        if math.isnan(change):
            continue
        change = max(-100.0, min(change, 200.0))
        if item.get("basket") in ("fixed", "irregular", "leak"):
            out.append({"basket": item["basket"], "change_pct": change})
            continue
        sub = item.get("subcategory")
        cat = normalize_category(item.get("category")) or (SUBCATEGORIES[sub][0] if sub in SUBCATEGORIES else None)
        if cat:
            out.append({"category": cat, "change_pct": change})
        elif item.get("merchant"):
            out.append({"merchant": str(item["merchant"]), "change_pct": change})
    if not out:
        raise ToolError("adjustments must contain at least one {category|basket, change_pct}")
    return out


async def _simulate_what_if(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    adjustments = _clean_adjustments(args.get("adjustments"))
    horizon = max(1, min(int(_num(args.get("horizon_months"), 12)), 120))
    ret = max(0.0, min(_num(args.get("invest_return_pct"), 0.0), 15.0))
    res = _jsonable(await call_analytics("whatif", "simulate_what_if", ctx.customer_id, adjustments, horizon_months=horizon, invest_return_pct=ret))
    payload = compact({k: res.get(k) for k in ("baseline_monthly", "new_monthly", "monthly_saving", "horizon_months", "total_saving", "with_return", "per_item")}, max_list=6)
    payload["adjustments"] = adjustments
    first = adjustments[0]
    target_key = "basket" if "basket" in first else ("category" if "category" in first else "merchant")
    slider = {target_key: first[target_key], "min": -100, "max": 0, "value": first["change_pct"]}
    widget = new_widget("what_if", {"base_adjustments": adjustments, "result": res, "slider": slider, "horizon_months": horizon, "invest_return_pct": ret})
    start, end = _window_months(ctx, 3)
    count = await _count_tx(ctx, start, end)
    summary = _s(ctx, f"Save {fmt_eur(_num(res.get('monthly_saving')))}/mo", f"Säästö {fmt_eur(_num(res.get('monthly_saving')), 'fi')}/kk", f"Sparar {fmt_eur(_num(res.get('monthly_saving')), 'sv')}/mån.")
    return ToolResult(payload, [widget], _sources(ctx, count, start, end), summary, res)


def _goal_widgets(goals: list[dict[str, Any]], loc: str) -> list[Widget]:
    if not goals:
        return []
    items = [
        {"label": f"{g.get('emoji') or GOAL_KIND_EMOJI.get(str(g.get('kind')), '🎯')} {g.get('name')}", "value": round(100 * _num(g.get("progress")), 1), "unit": "%", "tone": "good" if _num(g.get("progress")) >= 0.5 else "neutral"}
        for g in goals[:4]
    ]
    return [
        new_widget("kpi", {"items": items}),
        new_widget("action_buttons", {"buttons": [{"label": pick(loc, "Open goals", "Avaa tavoitteet", "Öppna sparmål"), "kind": "open_tab", "payload": {"tab": "goals"}}]}),
    ]


async def _list_goals(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    goals = _jsonable(await call_analytics("goals", "list_goals", ctx.customer_id)) or []
    payload = {"goals": [{k: g.get(k) for k in ("id", "name", "kind", "target_amount", "saved_amount", "deadline", "monthly_contribution", "progress")} for g in goals]}
    return ToolResult(payload, _goal_widgets(goals, ctx.locale), {"tx_count": 0, "period": "", "start": None, "end": None}, _s(ctx, f"{len(goals)} goals", f"{len(goals)} tavoitetta", f"{len(goals)} sparmål"), goals)


def _normalize_deadline(value: Any, as_of: date) -> str | None:
    d = parse_iso(value)
    if not d:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", str(value).strip()):
        # "2027-06" → end of that month
        nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
        d = date.fromordinal(nxt.toordinal() - 1)
    if d <= as_of:
        return None
    return d.isoformat()


def _goal_button_label(name: str, amount: float, deadline: str | None, loc: str) -> str:
    amount_txt = fmt_eur(amount, loc, 0)
    if loc == "fi":
        return f"Luo tavoite '{name}' {amount_txt}" + (f" ({deadline[:7]})" if deadline else "")
    if loc == "sv":
        return f"Skapa målet '{name}' {amount_txt}" + (f" senast {deadline[:7]}" if deadline else "")
    return f"Create goal '{name}' {amount_txt}" + (f" by {deadline[:7]}" if deadline else "")


async def _plan_goal(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    target = _num(args.get("target_amount"))
    if target <= 0:
        raise ToolError("target_amount must be a positive number of euros")
    name = (args.get("name") or "").strip() or pick(ctx.locale, "Goal", "Tavoite", "Mål")
    deadline = _normalize_deadline(args.get("deadline"), ctx.as_of)
    saved = max(0.0, _num(args.get("saved_amount")))
    res = _jsonable(await call_analytics("goals", "plan_goal", ctx.customer_id, target, deadline=deadline, name=name, saved_amount=saved))
    payload = compact(res, max_list=6)
    kind = guess_goal_kind(name)
    final_deadline = res.get("deadline") or deadline or res.get("suggested_deadline")
    goal_payload = {
        "name": res.get("name") or name,
        "target_amount": target,
        "deadline": final_deadline,
        "emoji": GOAL_KIND_EMOJI[kind],
        "kind": kind,
        "saved_amount": saved,
    }
    buttons = [{"label": _goal_button_label(goal_payload["name"], target, final_deadline, ctx.locale), "kind": "create_goal", "payload": goal_payload}]
    suggested = parse_iso(res.get("suggested_deadline"))
    current = parse_iso(final_deadline)
    if res.get("feasibility") in ("stretch", "unrealistic") and suggested and (not current or suggested > current):
        prompt = pick(ctx.locale, f"Plan the {int(target)} € goal for {res['suggested_deadline']} instead", f"Suunnittele tavoite {int(target)} € päivämäärään {res['suggested_deadline']}", f"Planera målet på {int(target)} € till {res['suggested_deadline']} i stället")
        buttons.append({"label": pick(ctx.locale, "Try a later deadline", "Kokeile myöhempää päivää", "Prova ett senare datum"), "kind": "prompt", "payload": {"text": prompt}})
    widgets = [new_widget("goal_plan", res), new_widget("action_buttons", {"buttons": buttons})]
    start, end = _window_months(ctx, 3)
    count = await _count_tx(ctx, start, end)
    payload["proposal"] = "Not saved yet: the app shows a 'Create goal' button the user can tap."
    if res.get("feasibility") == "unrealistic" and _num(res.get("current_monthly_surplus")) <= 0:
        payload["proposal"] = ("Not saved. Be honest: right now more money goes out than comes in, so this plan "
                               "is not affordable as it stands. Say that plainly, do not present it as achievable "
                               "and do not push the 'Create goal' button; suggest freeing up money first.")
    summary = _s(ctx, f"{name}: {fmt_eur(_num(res.get('needed_per_month')))}/mo · {res.get('feasibility')}", f"{name}: {fmt_eur(_num(res.get('needed_per_month')), 'fi')}/kk", f"{name}: {fmt_eur(_num(res.get('needed_per_month')), 'sv')}/mån.")
    return ToolResult(payload, widgets, _sources(ctx, count, start, end), summary, res)


async def _create_goal(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    name = (args.get("name") or "").strip()
    target = _num(args.get("target_amount"))
    if not name or target <= 0:
        raise ToolError("name and a positive target_amount are required")
    kind = args.get("kind") if args.get("kind") in GOAL_KINDS else guess_goal_kind(name)
    deadline = _normalize_deadline(args.get("deadline"), ctx.as_of)
    goal_payload = {"name": name, "target_amount": target, "deadline": deadline, "emoji": args.get("emoji") or GOAL_KIND_EMOJI[kind], "kind": kind, "saved_amount": max(0.0, _num(args.get("saved_amount")))}
    if not user_confirmed(ctx.user_text):
        button = {"label": _goal_button_label(name, target, deadline, ctx.locale), "kind": "create_goal", "payload": goal_payload}
        return ToolResult(
            {"status": "proposed_not_saved", "goal": goal_payload, "note": "User has not confirmed. Ask them to tap the button or say yes."},
            [new_widget("action_buttons", {"buttons": [button]})],
            {"tx_count": 0, "period": ""},
            _s(ctx, "Goal proposed", "Tavoite-ehdotus", "Förslag till mål"),
        )
    goal = _jsonable(await call_analytics("goals", "create_goal", ctx.customer_id, **goal_payload))
    return ToolResult(
        {"status": "saved", "goal": {k: goal.get(k) for k in ("id", "name", "target_amount", "saved_amount", "deadline", "monthly_contribution", "progress")}},
        _goal_widgets([goal], ctx.locale),
        {"tx_count": 0, "period": ""},
        _s(ctx, f"Goal saved: {name}", f"Tavoite tallennettu: {name}", f"Målet sparat: {name}"),
        goal,
    )


async def _update_goal(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    goal_id = str(args.get("goal_id") or "").strip()
    if not goal_id:
        raise ToolError("goal_id is required (get it from list_goals)")
    fields = {k: args[k] for k in ("name", "target_amount", "saved_amount", "deadline", "monthly_contribution") if args.get(k) not in (None, "")}
    if "deadline" in fields:
        fields["deadline"] = _normalize_deadline(fields["deadline"], ctx.as_of)
    if not fields:
        raise ToolError("no fields to update")
    if not user_confirmed(ctx.user_text):
        label = pick(ctx.locale, "Confirm change", "Vahvista muutos", "Bekräfta ändringen")
        prompt = pick(ctx.locale, "Yes, update the goal: ", "Kyllä, päivitä tavoite: ", "Ja, uppdatera målet: ") + json.dumps(fields, ensure_ascii=False)
        return ToolResult(
            {"status": "proposed_not_saved", "goal_id": goal_id, "fields": fields, "note": "Ask the user to confirm first."},
            [new_widget("action_buttons", {"buttons": [{"label": label, "kind": "prompt", "payload": {"text": prompt}}]})],
            {"tx_count": 0, "period": ""},
            _s(ctx, "Update proposed", "Muutosehdotus", "Förslag till ändring"),
        )
    goal = _jsonable(await call_analytics("goals", "update_goal", ctx.customer_id, goal_id, **fields))
    return ToolResult({"status": "saved", "goal": goal}, _goal_widgets([goal], ctx.locale), {"tx_count": 0, "period": ""}, _s(ctx, "Goal updated", "Tavoite päivitetty", "Målet uppdaterat"), goal)


async def _survival_plan(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    amount = args.get("amount")
    amount = _num(amount) if amount not in (None, "") else None
    until = parse_iso(args.get("until"))
    until_s = until.isoformat() if until and until > ctx.as_of else None
    res = _jsonable(await call_analytics("survival", "survival_plan", ctx.customer_id, amount=amount, until=until_s))
    payload = compact(res, max_list=6)
    start, end = _window_months(ctx, 3)
    count = await _count_tx(ctx, start, end)
    summary = _s(ctx, f"{fmt_eur(_num(res.get('per_day')))}/day · {res.get('risk')}", f"{fmt_eur(_num(res.get('per_day')), 'fi')}/päivä", f"{fmt_eur(_num(res.get('per_day')), 'sv')}/dag")
    return ToolResult(payload, [new_widget("survival_plan", res)], _sources(ctx, count, start, end), summary, res)


async def _home_readiness(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    price = args.get("property_price")
    price = _num(price) if price not in (None, "") and _num(price) > 0 else None
    res = _jsonable(await call_analytics("mortgage", "home_readiness", ctx.customer_id, property_price=price))
    payload = compact(res, max_list=6)
    start, end = _window_months(ctx, 12)
    count = await _count_tx(ctx, start, end)
    return ToolResult(payload, [new_widget("home_readiness", res)], _sources(ctx, count, start, end), _s(ctx, f"Verdict: {res.get('verdict')}", "Asuntolainavalmius", "Redo för bostadslån"), res)


async def _explain_concept(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    topic = str(args.get("topic") or "").strip()
    if not topic:
        raise ToolError("topic is required")
    lesson = find_lesson(topic, ctx.locale)
    payload = {"id": lesson["id"], "title": lesson["title"], "key_points": _first_sentences(lesson["body"], 3)}
    return ToolResult(payload, [new_widget("lesson", lesson)], {"tx_count": 0, "period": ""}, _s(ctx, f"Lesson: {lesson['title']}", f"Oppitunti: {lesson['title']}", f"Lektion: {lesson['title']}"), lesson)


def _first_sentences(text: str, n: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:n])


async def _render_chart(args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    chart_type = args.get("chart_type") if args.get("chart_type") in ("bar", "line", "donut") else "bar"
    unit = args.get("unit") if args.get("unit") in ("€", "%", "") else "€"
    title = str(args.get("title") or "")[:80]
    rows = []
    for row in (args.get("data") or [])[:24]:
        if isinstance(row, dict) and row.get("label") is not None:
            v = _num(row.get("value"), float("nan"))
            if math.isfinite(v) and abs(v) <= 1e12:  # 1e400 parses as infinity: not a chart value
                rows.append((str(row["label"])[:40], round(v, 2)))
    if not rows:
        raise ToolError("data must contain {label, value} rows taken from earlier tool results")
    if chart_type == "line":
        data = {"title": title, "unit": unit, "points": [{"x": l, "y": v} for l, v in rows]}
        kind = "line_chart"
    elif chart_type == "donut":
        data = {"title": title, "unit": unit, "slices": [{"label": l, "value": abs(v)} for l, v in rows]}
        kind = "donut_chart"
    else:
        top = max(abs(v) for _, v in rows)
        data = {"title": title, "unit": unit, "bars": [{"label": l, "value": v, "highlight": abs(v) == top} for l, v in rows]}
        kind = "bar_chart"
    return ToolResult({"rendered": kind, "points": len(rows)}, [new_widget(kind, data)], {"tx_count": 0, "period": ""}, _s(ctx, f"Chart: {title}", f"Kaavio: {title}", f"Diagram: {title}"))


EXECUTORS: dict[str, Executor] = {
    "get_overview": _get_overview,
    "query_spending": _query_spending,
    "search_transactions": _search_transactions,
    "get_baskets": _get_baskets,
    "safe_to_spend": _safe_to_spend,
    "recurring_payments": _recurring_payments,
    "spender_profile": _spender_profile,
    "benchmarks": _benchmarks,
    "simulate_what_if": _simulate_what_if,
    "list_goals": _list_goals,
    "plan_goal": _plan_goal,
    "create_goal": _create_goal,
    "update_goal": _update_goal,
    "survival_plan": _survival_plan,
    "home_readiness": _home_readiness,
    "explain_concept": _explain_concept,
    "render_chart": _render_chart,
}
assert set(EXECUTORS) == set(TOOL_NAMES), "every schema needs an executor"


async def execute_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
    """Run a tool by name. Never raises: errors become an error payload the model can read."""
    executor = EXECUTORS.get(name)
    if executor is None:
        return ToolResult({"error": f"unknown tool '{name}'", "available": list(TOOL_NAMES)}, error="unknown_tool", summary="unknown tool")
    try:
        with use_locale(ctx.locale):  # analytics texts and labels follow the turn language
            return await executor(args or {}, ctx)
    except ToolError as exc:
        return ToolResult({"error": str(exc)}, error="invalid_arguments", summary=str(exc)[:80])
    except Exception as exc:  # noqa: BLE001 - analytics failures must not kill the chat
        log.exception("Tool %s failed", name)
        return ToolResult({"error": f"{name} is temporarily unavailable ({type(exc).__name__})"}, error="tool_failed", summary="unavailable")


# =============================================================================== lessons

_BUILTIN_LESSONS: dict[str, dict[str, Any]] = {
    "three_baskets": {
        "emoji": "🧺",
        "keywords": ["basket", "kori", "korg", "fixed", "irregular", "leak", "vuoto", "läck"],
        "title": {"en": "The three money baskets", "fi": "Kolme rahakoria", "sv": "De tre pengakorgarna"},
        "body": {
            "en": "Every euro you spend lands in one of three baskets. Fixed essentials (rent, bills, groceries) keep your life running and are predictable. Irregular essentials (dentist, repairs, car) are certain to come but not on a schedule, so set a little aside monthly. Everyday leaks (takeaway, taxis, impulse buys) are optional and small, which is exactly why they add up unnoticed. Trim leaks first, plan irregulars, and keep fixed costs lean.",
            "fi": "Jokainen käyttämäsi euro päätyy yhteen kolmesta korista. Kiinteät välttämättömät (vuokra, laskut, ruoka) pitävät arjen käynnissä ja ovat ennustettavia. Epäsäännölliset välttämättömät (hammaslääkäri, korjaukset, auto) tulevat varmasti mutta eivät aikataulussa, joten varaa niihin vähän joka kuukausi. Arjen vuodot (noutoruoka, taksit, heräteostokset) ovat valinnaisia ja pieniä, ja juuri siksi ne kertyvät huomaamatta. Karsi ensin vuotoja, suunnittele epäsäännölliset ja pidä kiinteät kulut kurissa.",
            "sv": "Varje euro du lägger hamnar i en av tre korgar. Fasta måsten (hyra, räkningar, mat) håller vardagen igång och är förutsägbara. Oregelbundna måsten (tandläkare, reparationer, bil) kommer säkert men inte enligt schema, så lägg undan lite varje månad. Vardagsläckor (hämtmat, taxi, impulsköp) är valfria och små, och just därför växer de i det tysta. Täpp till läckorna först, planera för de oregelbundna och håll de fasta kostnaderna smala.",
        },
        "quiz": {"question": {"en": "Which basket does a dentist bill belong to?", "fi": "Mihin koriin hammaslääkärilasku kuuluu?", "sv": "Vilken korg hör en tandläkarräkning till?"}, "options": {"en": ["Fixed", "Irregular", "Leak"], "fi": ["Kiinteät", "Epäsäännölliset", "Vuodot"], "sv": ["Fasta", "Oregelbundna", "Läckor"]}, "answer_index": 1},
    },
    "emergency_fund": {
        "emoji": "🛟",
        "keywords": ["emergency", "buffer", "puskuri", "hätä", "rainy", "buffert", "nödfond"],
        "title": {"en": "Emergency fund", "fi": "Puskurirahasto", "sv": "Buffertsparande"},
        "body": {
            "en": "An emergency fund is money set aside only for surprises: a broken phone, a sudden trip home, a gap between jobs. A common target is one to three months of fixed costs. Without it, every surprise becomes debt or stress. Build it in small automatic transfers right after payday, and keep it in a separate account so it is not spent by accident.",
            "fi": "Puskurirahasto on vain yllätyksiin varattua rahaa: rikkoutunut puhelin, äkillinen matka tai väli töiden välissä. Yleinen tavoite on yhdestä kolmeen kuukauden kiinteät kulut. Ilman sitä jokaisesta yllätyksestä tulee velkaa tai stressiä. Kerrytä sitä pienillä automaattisilla siirroilla heti palkkapäivän jälkeen ja pidä se erillisellä tilillä.",
            "sv": "En buffert är pengar som är reserverade bara för överraskningar: en trasig telefon, en plötslig resa hem eller ett glapp mellan två jobb. Ett vanligt mål är en till tre månaders fasta kostnader. Utan buffert blir varje överraskning skuld eller stress. Bygg upp den med små automatiska överföringar direkt efter lönedagen och håll den på ett separat konto så att den inte används av misstag.",
        },
        "quiz": {"question": {"en": "A common emergency fund target is…", "fi": "Puskurirahaston yleinen tavoite on…", "sv": "Ett vanligt mål för bufferten är…"}, "options": {"en": ["One week of spending", "1–3 months of fixed costs", "One year of salary"], "fi": ["Viikon kulut", "1–3 kuukauden kiinteät kulut", "Vuoden palkka"], "sv": ["En veckas utgifter", "1–3 månaders fasta kostnader", "En årslön"]}, "answer_index": 1},
    },
    "compound_interest": {
        "emoji": "📈",
        "keywords": ["compound", "korkoa korolle", "interest", "korko", "growth", "ränta"],
        "title": {"en": "Compound growth", "fi": "Korkoa korolle", "sv": "Ränta på ränta"},
        "body": {
            "en": "Compound growth means your returns start earning returns of their own. Small amounts saved early can outgrow larger amounts saved later, because time does the heavy lifting. The flip side is debt: interest on unpaid balances compounds against you. Returns on investments are never guaranteed and values can fall as well as rise.",
            "fi": "Korkoa korolle tarkoittaa, että tuotot alkavat tuottaa itsekin. Varhain säästetyt pienet summat voivat kasvaa suuremmiksi kuin myöhemmin säästetyt isot, koska aika tekee raskaan työn. Kääntöpuoli on velka: maksamattoman saldon korko kasvaa sinua vastaan. Sijoitusten tuotot eivät ole koskaan taattuja, ja arvo voi myös laskea.",
            "sv": "Ränta på ränta betyder att avkastningen börjar ge egen avkastning. Små summor som sparas tidigt kan växa sig större än stora summor som sparas senare, eftersom tiden gör grovjobbet. Baksidan är skulder: räntan på obetalda saldon växer mot dig. Avkastning på placeringar är aldrig garanterad och värdet kan både stiga och sjunka.",
        },
        "quiz": {"question": {"en": "What makes compound growth powerful?", "fi": "Mikä tekee korkoa korolle -ilmiöstä voimakkaan?", "sv": "Vad gör ränta på ränta så kraftfull?"}, "options": {"en": ["Time", "Luck", "Big one-off deposits only"], "fi": ["Aika", "Tuuri", "Vain isot kertatalletukset"], "sv": ["Tiden", "Tur", "Bara stora engångsinsättningar"]}, "answer_index": 0},
    },
    "pay_yourself_first": {
        "emoji": "🐷",
        "keywords": ["pay yourself", "automatic", "automaatti", "save first", "säästä ensin", "betala dig själv", "spara först"],
        "title": {"en": "Pay yourself first", "fi": "Maksa ensin itsellesi", "sv": "Betala dig själv först"},
        "body": {
            "en": "Instead of saving whatever is left at the end of the month (usually nothing), move a fixed amount to savings the day your salary arrives. Then spend the rest freely. It works because it removes willpower from the equation: the decision is made once, not every day.",
            "fi": "Sen sijaan, että säästäisit kuun lopussa sen mitä jää (yleensä ei mitään), siirrä kiinteä summa säästöön palkkapäivänä. Käytä loput vapaasti. Tämä toimii, koska se poistaa tahdonvoiman yhtälöstä: päätös tehdään kerran, ei joka päivä.",
            "sv": "I stället för att spara det som blir över i slutet av månaden (oftast ingenting) flyttar du en fast summa till sparande samma dag som lönen kommer. Sedan använder du resten fritt. Det fungerar eftersom viljestyrkan försvinner ur ekvationen: beslutet fattas en gång, inte varje dag.",
        },
        "quiz": {"question": {"en": "When should the savings transfer happen?", "fi": "Milloin säästösiirto kannattaa tehdä?", "sv": "När ska sparöverföringen göras?"}, "options": {"en": ["On payday", "At the end of the month", "When I remember"], "fi": ["Palkkapäivänä", "Kuun lopussa", "Kun muistan"], "sv": ["På lönedagen", "I slutet av månaden", "När jag kommer ihåg"]}, "answer_index": 0},
    },
    "safe_to_spend": {
        "emoji": "🟢",
        "keywords": ["safe to spend", "turvallisesti", "afford", "varaa", "tryggt", "råd"],
        "title": {"en": "Safe-to-spend", "fi": "Turvallisesti käytettävissä", "sv": "Tryggt att använda"},
        "body": {
            "en": "Your balance is not your spending money. Safe-to-spend takes your balance, subtracts the bills still due before payday, a small buffer for irregular costs and your goal contributions, then divides the rest by the days left. It turns one scary number into a simple daily allowance.",
            "fi": "Saldo ei ole käyttörahaa. Turvallisesti käytettävä summa saadaan, kun saldosta vähennetään ennen palkkapäivää erääntyvät laskut, pieni puskuri epäsäännöllisiin menoihin ja säästötavoitteet, ja loput jaetaan jäljellä olevilla päivillä. Yhdestä pelottavasta luvusta tulee selkeä päiväraha.",
            "sv": "Ditt saldo är inte dina fickpengar. Tryggt att använda räknas så att man från saldot drar av räkningarna som förfaller före lönedagen, en liten buffert för oregelbundna utgifter och sparandet till dina mål, och delar resten med antalet dagar som är kvar. Ett skrämmande tal blir en enkel dagspeng.",
        },
        "quiz": {"question": {"en": "Is your whole balance safe to spend?", "fi": "Onko koko saldo turvallisesti käytettävissä?", "sv": "Är hela saldot tryggt att använda?"}, "options": {"en": ["Yes", "No — upcoming bills come first"], "fi": ["Kyllä", "Ei — tulevat laskut ensin"], "sv": ["Ja", "Nej — kommande räkningar går först"]}, "answer_index": 1},
    },
    "budgeting_50_30_20": {
        "emoji": "🥧",
        "keywords": ["50/30/20", "budget", "budjet"],
        "title": {"en": "The 50/30/20 rule", "fi": "50/30/20-sääntö", "sv": "50/30/20-regeln"},
        "body": {
            "en": "A simple starting budget: about 50 % of take-home pay to needs, 30 % to wants and 20 % to savings or paying off debt. It is a rule of thumb, not a law — with a small income, needs may take more. Compare it with your own fixed, irregular and leak baskets.",
            "fi": "Yksinkertainen aloitusbudjetti: noin 50 % nettotuloista tarpeisiin, 30 % haluihin ja 20 % säästöön tai velanmaksuun. Se on nyrkkisääntö, ei laki — pienillä tuloilla tarpeet voivat viedä enemmän. Vertaa sitä omiin kiinteisiin, epäsäännöllisiin ja vuotokoreihisi.",
            "sv": "En enkel startbudget: ungefär 50 % av nettolönen till behov, 30 % till önskemål och 20 % till sparande eller avbetalning av skulder. Det är en tumregel, inte en lag — med små inkomster kan behoven ta mer. Jämför den med dina egna korgar: fasta, oregelbundna och läckor.",
        },
        "quiz": {"question": {"en": "In 50/30/20, what is the 20?", "fi": "Mitä 20 tarkoittaa 50/30/20-säännössä?", "sv": "Vad står 20 för i 50/30/20?"}, "options": {"en": ["Wants", "Savings / debt", "Rent"], "fi": ["Halut", "Säästöt / velat", "Vuokra"], "sv": ["Önskemål", "Sparande / skulder", "Hyra"]}, "answer_index": 1},
    },
    "inflation": {
        "emoji": "🎈",
        "keywords": ["inflation", "inflaatio", "prices", "hinnat", "priser"],
        "title": {"en": "Inflation", "fi": "Inflaatio", "sv": "Inflation"},
        "body": {
            "en": "Inflation means prices rise over time, so the same euro buys a little less each year. Money sitting idle loses purchasing power. That is why long-term savings are often placed where they can grow, while short-term buffers stay safe and accessible.",
            "fi": "Inflaatio tarkoittaa hintojen nousua, joten sama euro ostaa joka vuosi vähän vähemmän. Käyttämätön raha menettää ostovoimaansa. Siksi pitkäaikaiset säästöt sijoitetaan usein kasvamaan, kun taas lyhyen ajan puskuri pidetään turvassa ja saatavilla.",
            "sv": "Inflation betyder att priserna stiger med tiden, så samma euro räcker till lite mindre varje år. Pengar som ligger stilla förlorar köpkraft. Därför placeras långsiktigt sparande ofta där det kan växa, medan en kortsiktig buffert hålls trygg och lättillgänglig.",
        },
        "quiz": {"question": {"en": "Inflation makes idle cash…", "fi": "Inflaatio tekee käyttämättömästä rahasta…", "sv": "Inflationen gör pengar som ligger stilla…"}, "options": {"en": ["Worth more", "Worth less", "Unchanged"], "fi": ["Arvokkaampaa", "Vähemmän arvokasta", "Ennallaan"], "sv": ["Mer värda", "Mindre värda", "Oförändrade"]}, "answer_index": 1},
    },
    "subscriptions": {
        "emoji": "🔁",
        "keywords": ["subscription", "tilaus", "recurring", "toistuva", "streaming", "prenumeration", "abonnemang"],
        "title": {"en": "Subscription creep", "fi": "Tilausten hiipivä kasvu", "sv": "Prenumerationer som smyger sig på"},
        "body": {
            "en": "Subscriptions are designed to be forgotten: small, automatic and easy to start. Five 10 € services are 600 € a year. Review recurring payments every few months and cancel anything you did not use in the last 30 days — you can always restart it.",
            "fi": "Tilaukset on suunniteltu unohdettaviksi: pieniä, automaattisia ja helppoja aloittaa. Viisi 10 euron palvelua on 600 € vuodessa. Käy toistuvat maksut läpi muutaman kuukauden välein ja peru kaikki, mitä et käyttänyt viimeisen 30 päivän aikana — voit aina aloittaa uudelleen.",
            "sv": "Prenumerationer är gjorda för att glömmas bort: små, automatiska och lätta att börja med. Fem tjänster för 10 € är 600 € om året. Gå igenom dina återkommande betalningar med några månaders mellanrum och säg upp allt du inte har använt de senaste 30 dagarna — du kan alltid börja igen.",
        },
        "quiz": {"question": {"en": "Five 10 € subscriptions cost per year…", "fi": "Viisi 10 euron tilausta maksaa vuodessa…", "sv": "Fem prenumerationer för 10 € kostar per år…"}, "options": {"en": ["120 €", "600 €", "50 €"], "fi": ["120 €", "600 €", "50 €"], "sv": ["120 €", "600 €", "50 €"]}, "answer_index": 1},
    },
    "investing_basics": {
        "emoji": "🌱",
        "keywords": ["invest", "sijoit", "fund", "rahasto", "stock", "osake", "etf", "placer", "fond", "aktie"],
        "title": {"en": "Investing basics", "fi": "Sijoittamisen perusteet", "sv": "Grunderna i att placera"},
        "body": {
            "en": "Investing means accepting risk for the chance of higher long-term returns. Basics: build a buffer first, invest only money you will not need for years, spread risk across many companies (for example broad funds), keep costs low and stay calm when markets fall. This is general education, not personal advice — S-Bank's advisors can help you choose.",
            "fi": "Sijoittaminen tarkoittaa riskin hyväksymistä mahdollisesti paremman pitkän aikavälin tuoton vuoksi. Perusteet: rakenna ensin puskuri, sijoita vain rahaa, jota et tarvitse vuosiin, hajauta riski moneen yhtiöön (esim. laajat rahastot), pidä kulut matalina ja pysy rauhallisena markkinoiden laskiessa. Tämä on yleistä tietoa, ei henkilökohtaista neuvontaa — S-Pankin asiantuntijat auttavat valinnoissa.",
            "sv": "Att placera betyder att man accepterar risk för chansen till högre avkastning på lång sikt. Grunderna: bygg först en buffert, placera bara pengar som du inte behöver på flera år, sprid risken på många företag (till exempel breda fonder), håll kostnaderna låga och behåll lugnet när marknaden faller. Det här är allmän information, inte personlig rådgivning — S-Bankens experter hjälper dig att välja.",
        },
        "quiz": {"question": {"en": "What should come before investing?", "fi": "Mikä kannattaa hoitaa ennen sijoittamista?", "sv": "Vad ska komma före placeringar?"}, "options": {"en": ["An emergency buffer", "A new phone", "Nothing"], "fi": ["Puskurirahasto", "Uusi puhelin", "Ei mitään"], "sv": ["En buffert", "En ny telefon", "Ingenting"]}, "answer_index": 0},
    },
    "mortgage_basics": {
        "emoji": "🏡",
        "keywords": ["mortgage", "asuntolaina", "home loan", "ltv", "down payment", "käsiraha", "home", "bostadslån", "insats"],
        "title": {"en": "Mortgage basics", "fi": "Asuntolainan perusteet", "sv": "Grunderna i bostadslån"},
        "body": {
            "en": "Banks lend most of a home's price but expect you to bring equity (in Finland typically 10 % for first-time buyers, 15 % otherwise). They also check that you could still pay if interest rates rose, so steady income and a track record of saving matter as much as the deposit itself.",
            "fi": "Pankki lainaa suurimman osan asunnon hinnasta, mutta odottaa omarahoitusta (Suomessa yleensä 10 % ensiasunnon ostajalta, muuten 15 %). Se myös varmistaa, että pystyisit maksamaan, vaikka korot nousisivat, joten vakaat tulot ja näyttö säästämisestä ovat yhtä tärkeitä kuin käsiraha.",
            "sv": "Banken lånar ut största delen av bostadens pris men förväntar sig en egen insats (i Finland vanligen 10 % för förstagångsköpare, annars 15 %). Banken kontrollerar också att du klarar betalningarna även om räntorna stiger, så stabila inkomster och bevis på regelbundet sparande är lika viktiga som själva insatsen.",
        },
        "quiz": {"question": {"en": "Typical equity for a first-time buyer in Finland?", "fi": "Ensiasunnon ostajan tyypillinen omarahoitus Suomessa?", "sv": "Vanlig egen insats för en förstagångsköpare i Finland?"}, "options": {"en": ["0 %", "10 %", "50 %"], "fi": ["0 %", "10 %", "50 %"], "sv": ["0 %", "10 %", "50 %"]}, "answer_index": 1},
    },
    "impulse_spending": {
        "emoji": "⚡",
        "keywords": ["impulse", "heräte", "late night", "yöllä", "treat", "impuls"],
        "title": {"en": "Beating impulse spending", "fi": "Heräteostosten selättäminen", "sv": "Så slår du impulsköpen"},
        "body": {
            "en": "Impulse purchases happen when emotion is high and friction is low: tired, late at night, one tap away. Add friction: wait 24 hours before non-essential buys over 30 €, remove saved cards from shopping apps, and decide your treat budget in advance so enjoying it is guilt-free.",
            "fi": "Heräteostoksia syntyy, kun tunteet ovat pinnalla ja kynnys on matala: väsyneenä, myöhään illalla, yhden napautuksen päässä. Lisää kitkaa: odota vuorokausi ennen yli 30 euron turhia ostoksia, poista tallennetut kortit ostossovelluksista ja päätä herkkubudjetti etukäteen, niin siitä voi nauttia ilman syyllisyyttä.",
            "sv": "Impulsköp uppstår när känslorna är starka och tröskeln låg: trött, sent på kvällen, ett tryck bort. Höj tröskeln: vänta ett dygn före onödiga köp över 30 €, ta bort sparade kort från shoppingappar och bestäm din godisbudget i förväg, så kan du njuta av den utan dåligt samvete.",
        },
        "quiz": {"question": {"en": "A good rule against impulse buys is…", "fi": "Hyvä sääntö heräteostoksia vastaan on…", "sv": "En bra regel mot impulsköp är…"}, "options": {"en": ["Buy immediately", "Wait 24 hours", "Use credit"], "fi": ["Osta heti", "Odota vuorokausi", "Käytä luottoa"], "sv": ["Köp direkt", "Vänta ett dygn", "Använd kredit"]}, "answer_index": 1},
    },
}


def _loc(value: Any, locale: str) -> Any:
    if isinstance(value, dict) and ("en" in value or "fi" in value or "sv" in value):
        return value.get(locale) or value.get("en") or next(iter(value.values()))
    return value


@lru_cache(maxsize=1)
def _load_lessons_file() -> list[dict[str, Any]]:
    """Read ``app/data/lessons.json`` defensively (it is owned by the content builder)."""
    path = APP_DATA_DIR / "lessons.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        log.warning("lessons.json unreadable; using built-in lessons")
        return []
    if isinstance(raw, dict):
        for key in ("lessons", "items", "data"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]
        # maybe a mapping id → lesson
        return [dict(v, id=v.get("id", k)) for k, v in raw.items() if isinstance(v, dict)]
    return [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []


def _lesson_body(lesson: dict[str, Any], locale: str) -> str:
    for key in ("body", "content", "text", "summary", "description"):
        value = _loc(lesson.get(key), locale)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, list):
            parts = [(_loc(p, locale) if not isinstance(p, dict) else _loc(p.get("text") or p.get("body") or "", locale)) for p in value]
            text = " ".join(str(p) for p in parts if p)
            if text:
                return text
    cards = lesson.get("cards") or lesson.get("steps") or lesson.get("sections")
    if isinstance(cards, list):
        return " ".join(str(_loc(c.get("body") or c.get("text") or "", locale)) for c in cards if isinstance(c, dict)).strip()
    return ""


def _lesson_quiz(lesson: dict[str, Any], locale: str) -> dict[str, Any] | None:
    quiz = lesson.get("quiz")
    if isinstance(quiz, list) and quiz:
        quiz = quiz[0]
    if not isinstance(quiz, dict):
        return None
    question = _loc(quiz.get("question") or quiz.get("q"), locale)
    options = _loc(quiz.get("options") or quiz.get("choices"), locale)
    answer = quiz.get("answer_index", quiz.get("answer", quiz.get("correct", 0)))
    if not question or not isinstance(options, list):
        return None
    if isinstance(answer, str) and answer in options:
        answer = options.index(answer)
    return {"question": str(question), "options": [str(_loc(o, locale)) for o in options], "answer_index": int(_num(answer))}


def find_lesson(topic: str, locale: str = "en") -> dict[str, Any]:
    """Find the best lesson for ``topic`` in lessons.json, else in the built-in set.

    Returns the ``lesson`` widget shape: ``{id, title, body, emoji, quiz?}``.
    """
    loc = norm_locale(locale)
    words = {w for w in re.split(r"[\s_\-/,]+", topic.lower()) if len(w) > 2}
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for lesson in _load_lessons_file():
        lid = str(lesson.get("id", "")).lower()
        hay = " ".join(
            str(x).lower()
            for x in (lid, _loc(lesson.get("title"), loc), _loc(lesson.get("title"), "en"), " ".join(map(str, lesson.get("tags") or lesson.get("concepts") or lesson.get("keywords") or [])))
        )
        score = 3.0 if lid == topic.lower() else sum(1.0 for w in words if w in hay)
        if score > best[0]:
            best = (score, lesson)
    if best[1] is not None and best[0] >= 1:
        lesson = best[1]
        body = _lesson_body(lesson, loc)
        if body:
            out = {"id": str(lesson.get("id")), "title": str(_loc(lesson.get("title"), loc)), "body": body, "emoji": str(lesson.get("emoji") or "💡")}
            quiz = _lesson_quiz(lesson, loc)
            if quiz:
                out["quiz"] = quiz
            return out
    # built-in fallback
    key = topic.lower().replace(" ", "_")
    if key not in _BUILTIN_LESSONS:
        scored = [(sum(1 for kw in v["keywords"] if kw in topic.lower()) + sum(1 for w in words if w in k), k) for k, v in _BUILTIN_LESSONS.items()]
        scored.sort(reverse=True)
        key = scored[0][1] if scored and scored[0][0] > 0 else "three_baskets"
    item = _BUILTIN_LESSONS[key]
    quiz = item["quiz"]
    return {
        "id": key,
        "title": _loc(item["title"], loc),
        "body": _loc(item["body"], loc),
        "emoji": item["emoji"],
        "quiz": {"question": _loc(quiz["question"], loc), "options": _loc(quiz["options"], loc), "answer_index": quiz["answer_index"]},
    }
