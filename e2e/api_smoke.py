#!/usr/bin/env python3
"""SPankkiBot API smoke test — validates every REST route of docs/SPEC.md §3.2 and the
POST /api/chat SSE protocol (§4.2) against a running backend.

    uv run --with httpx python e2e/api_smoke.py [--base http://localhost:8000]
        [--customers CUST05020,CUST00584] [--skip-chat] [--json report.json] [--slow-ms 1500]

Hard failures (wrong status, missing keys, wrong types, broken SSE order) -> FAIL, exit code 1.
Soft issues (latency, counts that differ from SPEC suggestions) -> WARN, exit code 0.
Side effects: creates one temporary goal per customer and deletes it again; posts one chat feedback.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

try:
    import httpx
except ImportError:  # pragma: no cover
    sys.exit("httpx missing — run with: uv run --with httpx python e2e/api_smoke.py")

DEFAULT_CUSTOMERS = ["CUST05020", "CUST00584"]
ALL_DEMO_IDS = {"CUST05020", "CUST00584", "CUST00586", "CUST00961", "CUST00001"}
CHAT_QUESTIONS = [
    # (persona, locale, question, expect_widget)
    ("sisu", "en", "How much did I spend on restaurants last month?", True),
    ("aava", "en", "What is safe for me to spend this week?", True),
    ("sisu", "fi", "Millainen kuluttaja olen?", False),
]

# ───────────────────────────── tiny schema DSL ─────────────────────────────


class Spec:
    def check(self, v: Any, path: str, errs: list[str]) -> None:  # pragma: no cover
        raise NotImplementedError


@dataclass
class T(Spec):
    """Primitive type check. kind in num|int|str|bool|dict|list|any|date|datetime."""

    kind: str
    lo: float | None = None
    hi: float | None = None

    def check(self, v, path, errs):
        k = self.kind
        ok = {
            "num": isinstance(v, (int, float)) and not isinstance(v, bool),
            "int": isinstance(v, int) and not isinstance(v, bool),
            "str": isinstance(v, str),
            "bool": isinstance(v, bool),
            "dict": isinstance(v, dict),
            "list": isinstance(v, list),
            "any": True,
            "date": isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}", v)),
            "datetime": isinstance(v, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", v)),
            "scalar": isinstance(v, (str, int, float)) and not isinstance(v, bool),
        }[k]
        if not ok:
            errs.append(f"{path}: expected {k}, got {type(v).__name__} {_short(v)}")
            return
        if k in ("num", "int") and ((self.lo is not None and v < self.lo) or (self.hi is not None and v > self.hi)):
            errs.append(f"{path}: {v} outside [{self.lo}, {self.hi}]")


@dataclass
class Opt(Spec):
    inner: Spec

    def check(self, v, path, errs):
        if v is not None:
            self.inner.check(v, path, errs)


@dataclass
class Enum(Spec):
    values: tuple

    def __init__(self, *values):
        self.values = values

    def check(self, v, path, errs):
        if v not in self.values:
            errs.append(f"{path}: {_short(v)} not in {list(self.values)}")


@dataclass
class L(Spec):
    item: Spec
    min_len: int = 0
    max_len: int | None = None

    def check(self, v, path, errs):
        if not isinstance(v, list):
            errs.append(f"{path}: expected list, got {type(v).__name__}")
            return
        if len(v) < self.min_len:
            errs.append(f"{path}: expected ≥{self.min_len} items, got {len(v)}")
        if self.max_len is not None and len(v) > self.max_len:
            errs.append(f"{path}: expected ≤{self.max_len} items, got {len(v)}")
        for i, it in enumerate(v[:25]):
            self.item.check(it, f"{path}[{i}]", errs)


@dataclass
class O(Spec):
    """Object with required keys (extra keys allowed). `optional` keys are validated if present."""

    fields: dict[str, Spec]
    optional: dict[str, Spec] = field(default_factory=dict)
    any_of: list[tuple[str, ...]] = field(default_factory=list)  # at least one key of each tuple

    def check(self, v, path, errs):
        if not isinstance(v, dict):
            errs.append(f"{path or '$'}: expected object, got {type(v).__name__} {_short(v)}")
            return
        for k, s in self.fields.items():
            if k not in v:
                errs.append(f"{path}.{k}: missing")
            else:
                s.check(v[k], f"{path}.{k}", errs)
        for k, s in self.optional.items():
            if k in v:
                s.check(v[k], f"{path}.{k}", errs)
        for group in self.any_of:
            if not any(g in v for g in group):
                errs.append(f"{path}: needs one of {list(group)}")


@dataclass
class OneOf(Spec):
    options: list[Spec]

    def check(self, v, path, errs):
        last: list[str] = []
        for o in self.options:
            e: list[str] = []
            o.check(v, path, e)
            if not e:
                return
            last = e
        errs.extend(last)


def _short(v: Any, n: int = 60) -> str:
    s = json.dumps(v, ensure_ascii=False, default=str) if not isinstance(v, str) else repr(v)
    return s if len(s) <= n else s[: n - 1] + "…"


NUM, INT, STR, BOOL, DICT, ANY, DATE = T("num"), T("int"), T("str"), T("bool"), T("dict"), T("any"), T("date")
BASKET5 = Enum("fixed", "irregular", "leak", "income", "saving")

# ───────────────────────────── SPEC shapes ─────────────────────────────

TX = O(
    {
        "id": T("scalar"),
        "date": DATE,
        "timestamp": T("datetime"),
        "amount": NUM,
        "category": STR,
        "basket": BASKET5,
        "merchant_id": Opt(STR),
        "merchant_label": Opt(STR),
        "mcc": Opt(T("scalar")),
        "mcc_label": Opt(STR),
        "icon": STR,
        "balance_after": NUM,
        "type": STR,
    }
)
GOAL = O(
    {
        "id": T("scalar"),
        "name": STR,
        "emoji": Opt(STR),
        "kind": Enum("car", "travel", "home", "emergency", "education", "gadget", "other"),
        "target_amount": NUM,
        "saved_amount": NUM,
        "deadline": Opt(DATE),
        "monthly_contribution": Opt(NUM),
        "progress": T("num", 0, 1),
        "created_at": STR,
    }
)
NUDGE = O({"id": T("scalar"), "kind": Enum("celebrate", "warn", "tip", "goal"), "text": STR, "emoji": STR, "action_prompt": Opt(STR)})
SAFE = O(
    {
        "balance": NUM,
        "next_payday": Opt(DATE),
        "days_until_payday": Opt(NUM),
        "upcoming_bills": L(O({"label": STR, "amount": NUM, "expected_date": Opt(DATE)})),
        "irregular_buffer": NUM,
        "goal_contributions": NUM,
        "safe_total": NUM,
        "safe_per_day": NUM,
        "safe_this_week": NUM,
        "status": Enum("comfortable", "tight", "critical"),
        "explanation": STR,
    }
)
TREND = L(O({"date": DATE, "balance": NUM}), min_len=1)
BY_BASKET = O({"fixed": NUM, "irregular": NUM, "leak": NUM})
HEALTH = O({"status": Enum("ok"), "as_of": DATE, "llm": O({"primary": BOOL})})
DEMO = L(O({"customer_id": STR, "name": STR, "age": NUM, "postal_code": STR, "tagline": STR, "avatar_emoji": STR}), min_len=2)
OVERVIEW = O(
    {
        "customer": O({"name": STR, "age": NUM, "postal_code": STR}, any_of=[("id", "customer_id")]),
        "as_of": DATE,
        "balance": NUM,
        "trend_30d": TREND,
        "month": O({"income": NUM, "spent": NUM, "saved": NUM, "by_basket": BY_BASKET}),
        "safe_to_spend": SAFE,
        "goals": L(GOAL),
        "recent_transactions": L(TX, max_len=8),
        "nudges": L(NUDGE),
    }
)
TX_PAGE = O({"items": L(TX), "total_count": INT})
GROUP = O({"key": T("scalar"), "label": STR, "total": NUM, "count": INT})
SPENDING = O(
    {
        "filters": DICT,
        "total": NUM,
        "count": INT,
        "avg_tx": NUM,
        "groups": L(GROUP),
        "period": O({"start": Opt(DATE), "end": Opt(DATE)}),
    }
)
BASKET_MONTH = O({"month": STR, "fixed": NUM, "irregular": NUM, "leak": NUM, "income": NUM, "saving": NUM})
TOP = L(O({"label": STR, "total": NUM}))
BASKETS = O(
    {
        "months": L(BASKET_MONTH, min_len=1),
        "current_month": O(
            {"fixed": NUM, "irregular": NUM, "leak": NUM, "income": NUM, "saving": NUM,
             "top": O({"fixed": TOP, "irregular": TOP, "leak": TOP})}
        ),
        "explanations": O({"fixed": STR, "irregular": STR, "leak": STR}),
    }
)
RECURRING = O(
    {
        "items": L(
            O(
                {"label": STR, "category": STR, "merchant_id": Opt(STR), "avg_amount": NUM, "cadence": STR,
                 "day_of_month": Opt(NUM), "last_date": DATE, "basket": BASKET5}
            )
        ),
        "monthly_total": NUM,
    }
)
PROFILE = O(
    {
        "archetype": O(
            {"key": Enum("steady_planner", "weekend_treater", "latte_leaker", "impulse_splurger", "squirrel_saver", "tightrope_walker"),
             "name": STR, "emoji": STR, "description": STR}
        ),
        "traits": L(O({"key": STR, "label": STR, "score": T("num", 0, 100), "detail": STR}), min_len=1),
        "savings_rate": NUM,
        "leak_share": NUM,
        "weekend_share": NUM,
        "small_tx_per_week": NUM,
        "late_night_share": NUM,
        "volatility": NUM,
    }
)
BENCH_ROW = O({"you_monthly": NUM, "peer_median_monthly": NUM, "peer_p25": NUM, "peer_p75": NUM, "percentile": NUM},
              optional={"stat_fi_monthly": Opt(NUM)})
BENCHMARKS = O(
    {
        "peer_group": O({"label": STR, "size": INT}),
        "categories": L(O({"category": STR, **BENCH_ROW.fields}, optional=BENCH_ROW.optional), min_len=1),
        "income": DICT,
        "savings_rate": DICT,
        "sources": L(O({"name": STR, "url": STR, "note": Opt(STR)})),
    }
)
WHAT_IF = O(
    {
        "baseline_monthly": NUM,
        "new_monthly": NUM,
        "monthly_saving": NUM,
        "horizon_months": INT,
        "total_saving": NUM,
        "with_return": NUM,
        "per_item": L(DICT),
        "series": L(O({"month": INT, "cumulative": NUM}), min_len=1),
    }
)
CUT = O({"label": STR, "category": Opt(STR), "basket": Opt(STR), "current_monthly": NUM, "cut_pct": NUM, "monthly_saving": NUM, "why": STR})
GOAL_PLAN = O(
    {
        "name": Opt(STR),
        "target_amount": NUM,
        "saved_amount": NUM,
        "deadline": Opt(DATE),
        "months": NUM,
        "needed_per_month": NUM,
        "current_monthly_surplus": NUM,
        "gap": NUM,
        "feasibility": Enum("on_track", "stretch", "unrealistic"),
        "suggested_deadline": Opt(DATE),
        "cuts": L(CUT),
        "cuts_total": NUM,
        "summary": STR,
    }
)
SURVIVAL = O(
    {
        "amount": NUM,
        "until": DATE,
        "days": NUM,
        "upcoming_bills_total": NUM,
        "bills": L(DICT),
        "free_money": NUM,
        "per_day": NUM,
        "per_week": NUM,
        "category_budgets": L(O({"category": STR, "budget": NUM, "typical": NUM})),
        "risk": Enum("ok", "tight", "short"),
        "shortfall": NUM,
        "tips": L(STR),
    }
)
HOME = O(
    {
        "property_price": NUM,
        "loan_needed": NUM,
        "equity_needed": NUM,
        "your_equity_estimate": NUM,
        "required_monthly_income": NUM,
        "your_monthly_income": NUM,
        "ltv": NUM,
        "verdict": Enum("ready", "almost", "not_yet"),
        "gaps": L(STR),
        "dataset_note": STR,
        "customer_application": Opt(DICT),
    }
)
LESSON_ITEM = O({"id": T("scalar")}, optional={"title": STR})
LESSONS = OneOf([L(LESSON_ITEM, min_len=1), O({"lessons": L(LESSON_ITEM, min_len=1)})])
PERSONAS = OneOf([T("list"), T("dict")])
FEEDBACK_ANY = OneOf([T("dict"), T("list"), T("str"), T("bool")])

WIDGET_TYPES = {
    "kpi", "bar_chart", "line_chart", "donut_chart", "basket_breakdown", "safe_to_spend", "goal_plan", "what_if",
    "transaction_list", "spender_profile", "benchmark", "survival_plan", "home_readiness", "lesson", "action_buttons",
}
WIDGET_DATA: dict[str, Spec] = {
    "kpi": O({"items": L(O({"label": STR, "value": NUM}, optional={"unit": STR, "delta": Opt(NUM), "tone": Opt(Enum("good", "bad", "neutral"))}), min_len=1)}),
    "bar_chart": O({"bars": L(O({"label": STR, "value": NUM}), min_len=1)}, optional={"title": STR, "unit": STR}),
    "line_chart": O({"points": L(O({"x": T("scalar"), "y": NUM}), min_len=1)}, optional={"title": STR, "unit": STR}),
    "donut_chart": O({"slices": L(O({"label": STR, "value": NUM}), min_len=1)}, optional={"title": STR}),
    "basket_breakdown": O({"fixed": NUM, "irregular": NUM, "leak": NUM}, optional={"explanations": DICT, "top": DICT}),
    "safe_to_spend": SAFE,
    "goal_plan": GOAL_PLAN,
    "what_if": O({"result": WHAT_IF}, optional={"slider": DICT}),
    "transaction_list": O({"items": L(TX)}, optional={"title": STR, "total": Opt(NUM)}),
    "spender_profile": PROFILE,
    "survival_plan": SURVIVAL,
    "home_readiness": HOME,
    "lesson": O({"id": T("scalar"), "title": STR, "body": STR}),
    "action_buttons": O({"buttons": L(O({"label": STR, "kind": Enum("prompt", "create_goal", "open_tab")}), min_len=1)}),
    "benchmark": DICT,
}
SSE_SHAPES: dict[str, Spec] = {
    "status": O({"state": Enum("thinking", "tool", "writing"), "label": STR}),
    "tool": O({"name": STR, "args": OneOf([T("dict"), T("str")]), "summary": Opt(STR)}),
    "widget": O({"id": T("scalar"), "type": STR, "data": ANY}),
    "token": O({"text": STR}),
    "done": O(
        {
            "message_id": T("scalar"),
            "sources": O({"tx_count": INT, "period": Opt(STR), "tools": L(STR)}),
            "suggestions": L(STR),
            "mood": Enum("happy", "neutral", "concerned", "celebrate"),
        }
    ),
    "error": O({"message": STR}),
}

# ───────────────────────────── runner ─────────────────────────────


@dataclass
class Result:
    name: str
    customer: str
    ok: bool
    ms: float
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: str = ""


class Smoke:
    def __init__(self, base: str, timeout: float, slow_ms: float):
        self.base = base.rstrip("/")
        self.api = self.base + "/api"
        self.client = httpx.Client(timeout=timeout, headers={"Accept": "application/json"})
        self.slow_ms = slow_ms
        self.results: list[Result] = []

    # generic request + validate
    def call(
        self,
        name: str,
        method: str,
        path: str,
        spec: Spec | None,
        *,
        cust: str = "-",
        params: dict | None = None,
        body: Any = None,
        expect: tuple[int, ...] = (200, 201),
        extra: Callable[[Any, list[str], list[str]], None] | None = None,
    ) -> Any:
        url = self.api + path
        errs: list[str] = []
        warns: list[str] = []
        data: Any = None
        t0 = time.perf_counter()
        try:
            r = self.client.request(method, url, params=params, json=body)
            ms = (time.perf_counter() - t0) * 1000
        except httpx.HTTPError as e:
            ms = (time.perf_counter() - t0) * 1000
            self.results.append(Result(name, cust, False, ms, [f"{type(e).__name__}: {e}"]))
            return None
        if r.status_code not in expect:
            errs.append(f"HTTP {r.status_code} (expected {expect}): {r.text[:200]}")
        else:
            try:
                data = r.json() if r.content else None
            except ValueError:
                errs.append(f"non-JSON body: {r.text[:120]}")
            if not errs and spec is not None:
                spec.check(data, "$", errs)
            if not errs and extra is not None:
                try:
                    extra(data, errs, warns)
                except Exception as e:  # validator bug or unexpected shape
                    errs.append(f"extra check crashed: {type(e).__name__}: {e}")
        if ms > self.slow_ms:
            warns.append(f"slow: {ms:.0f} ms > {self.slow_ms:.0f} ms")
        self.results.append(Result(name, cust, not errs, ms, errs, warns, _info(data)))
        return data if not errs else None

    # ── per-customer REST suite ──
    def customer_suite(self, c: str) -> None:
        P = f"/customers/{c}"

        def ov_extra(d, errs, warns):
            if len(d["recent_transactions"]) != 8:
                warns.append(f"recent_transactions has {len(d['recent_transactions'])} items (SPEC: 8)")
            if not (3 <= len(d["nudges"]) <= 6):
                warns.append(f"{len(d['nudges'])} nudges (SPEC: 3-6)")
            if len(d["goals"]) < 2 and c in ALL_DEMO_IDS:
                warns.append(f"demo customer has {len(d['goals'])} goals (SPEC: 2 seeded)")
            if d["as_of"][:10] > "2026-09-30":
                errs.append(f"as_of {d['as_of']} beyond dataset range")
            for t in d["recent_transactions"]:
                if t["date"][:10] > d["as_of"][:10]:
                    errs.append(f"transaction {t['id']} dated {t['date']} is after as_of {d['as_of']}")
                    break
            if abs(d["balance"] - d["safe_to_spend"]["balance"]) > 0.01:
                warns.append("overview.balance != safe_to_spend.balance")

        self.call("GET overview", "GET", f"{P}/overview", OVERVIEW, cust=c, extra=ov_extra)

        def tx_limit(d, errs, warns):
            if len(d["items"]) > 5:
                errs.append(f"limit=5 returned {len(d['items'])} items")
            if d["total_count"] < len(d["items"]):
                errs.append("total_count < len(items)")
            if d["total_count"] == 0:
                warns.append("no transactions returned")
            dates = [t["timestamp"] for t in d["items"]]
            if dates != sorted(dates, reverse=True) and dates != sorted(dates):
                warns.append("items are not sorted by time")

        self.call("GET transactions", "GET", f"{P}/transactions", TX_PAGE, cust=c, params={"limit": 5}, extra=tx_limit)

        def only_cat(cat):
            def f(d, errs, warns):
                bad = [t["category"] for t in d["items"] if t["category"] != cat]
                if bad:
                    errs.append(f"category filter leaked: {bad[:3]}")
            return f

        self.call("GET transactions ?category", "GET", f"{P}/transactions", TX_PAGE, cust=c,
                  params={"category": "Restaurants", "limit": 20}, extra=only_cat("Restaurants"))

        def only_leak(d, errs, warns):
            bad = [t["basket"] for t in d["items"] if t["basket"] != "leak"]
            if bad:
                errs.append(f"basket filter leaked: {bad[:3]}")

        self.call("GET transactions ?basket&date", "GET", f"{P}/transactions", TX_PAGE, cust=c,
                  params={"basket": "leak", "start": "2026-08-01", "end": "2026-08-31", "limit": 50, "offset": 0}, extra=only_leak)

        def by_cat(d, errs, warns):
            if not d["groups"]:
                warns.append("no groups for group_by=category")
            s = round(sum(g["total"] for g in d["groups"]), 2)
            if d["groups"] and abs(s - d["total"]) > max(1.0, abs(d["total"]) * 0.01) and len(d["groups"]) < 20:
                warns.append(f"sum(groups)={s} != total={d['total']}")

        self.call("GET spending ?group_by=category", "GET", f"{P}/spending", SPENDING, cust=c,
                  params={"start": "2026-08-01", "end": "2026-08-31", "group_by": "category"}, extra=by_cat)

        def by_basket(d, errs, warns):
            keys = {str(g["key"]) for g in d["groups"]}
            if not keys <= {"fixed", "irregular", "leak", "income", "saving"}:
                errs.append(f"unexpected basket keys {sorted(keys)}")

        self.call("GET spending ?group_by=basket", "GET", f"{P}/spending", SPENDING, cust=c, params={"group_by": "basket"}, extra=by_basket)
        self.call("GET spending ?category&month", "GET", f"{P}/spending", SPENDING, cust=c,
                  params={"category": "Restaurants", "group_by": "month"})

        def b_extra(d, errs, warns):
            if len(d["months"]) > 6:
                errs.append(f"months=6 returned {len(d['months'])} months")

        self.call("GET baskets ?months=6", "GET", f"{P}/baskets", BASKETS, cust=c, params={"months": 6}, extra=b_extra)
        self.call("GET safe-to-spend", "GET", f"{P}/safe-to-spend", SAFE, cust=c)
        self.call("GET recurring", "GET", f"{P}/recurring", RECURRING, cust=c)
        self.call("GET profile", "GET", f"{P}/profile", PROFILE, cust=c)
        self.call("GET benchmarks", "GET", f"{P}/benchmarks", BENCHMARKS, cust=c)

        def wi_extra(d, errs, warns):
            if d["horizon_months"] != 12:
                errs.append(f"horizon_months {d['horizon_months']} != 12")
            if d["monthly_saving"] < 0:
                errs.append(f"cutting restaurants by 20% gives negative saving {d['monthly_saving']}")
            if len(d["series"]) != 12:
                warns.append(f"series has {len(d['series'])} points (expected 12)")

        self.call("POST what-if", "POST", f"{P}/what-if", WHAT_IF, cust=c,
                  body={"adjustments": [{"category": "Restaurants", "change_pct": -20}], "horizon_months": 12, "invest_return_pct": 0.0},
                  extra=wi_extra)
        self.call("POST what-if (basket)", "POST", f"{P}/what-if", WHAT_IF, cust=c,
                  body={"adjustments": [{"basket": "leak", "change_pct": -30}], "horizon_months": 6, "invest_return_pct": 3.0})

        goals = self.call("GET goals", "GET", f"{P}/goals", L(GOAL), cust=c)
        if goals is not None and c in ALL_DEMO_IDS and len(goals) < 2:
            self.results[-1].warnings.append(f"{len(goals)} seeded goals (SPEC: 2)")

        created = self.call(
            "POST goals (create)", "POST", f"{P}/goals", GOAL, cust=c,
            body={"name": "E2E smoke goal", "target_amount": 999.0, "deadline": "2027-06-30", "emoji": "🧪", "kind": "other", "saved_amount": 10.0},
            extra=lambda d, e, w: (d["name"] != "E2E smoke goal" and e.append("name not echoed"))
            or (abs(d["target_amount"] - 999.0) > 0.01 and e.append("target_amount not echoed")),
        )
        if created is not None:
            gid = created["id"]
            self.call(
                "PATCH goals/{id}", "PATCH", f"{P}/goals/{gid}", GOAL, cust=c, body={"saved_amount": 100.0},
                extra=lambda d, e, w: abs(d["saved_amount"] - 100.0) > 0.01 and e.append(f"saved_amount={d['saved_amount']} after PATCH 100"),
            )
            self.call("DELETE goals/{id}", "DELETE", f"{P}/goals/{gid}", None, cust=c, expect=(200, 202, 204))
            self.call(
                "GET goals (after delete)", "GET", f"{P}/goals", L(GOAL), cust=c,
                extra=lambda d, e, w: any(str(g["id"]) == str(gid) for g in d) and e.append("deleted goal still listed"),
            )
        else:
            for n in ("PATCH goals/{id}", "DELETE goals/{id}"):
                self.results.append(Result(n, c, False, 0, ["skipped: create failed"]))

        def plan_extra(d, errs, warns):
            if abs(d["target_amount"] - 12000) > 0.01:
                errs.append("target_amount not echoed")
            if d["gap"] > 0 and not d["cuts"]:
                warns.append("gap > 0 but no cuts suggested")

        self.call("POST goals/plan", "POST", f"{P}/goals/plan", GOAL_PLAN, cust=c,
                  body={"target_amount": 12000, "deadline": "2027-06-30", "name": "Car", "saved_amount": 0}, extra=plan_extra)
        self.call("GET survival", "GET", f"{P}/survival", SURVIVAL, cust=c)
        self.call("GET survival ?amount=300", "GET", f"{P}/survival", SURVIVAL, cust=c, params={"amount": 300},
                  extra=lambda d, e, w: abs(d["amount"] - 300) > 0.01 and e.append(f"amount {d['amount']} != 300"))
        self.call("GET home-readiness", "GET", f"{P}/home-readiness", HOME, cust=c, params={"property_price": 250000},
                  extra=lambda d, e, w: abs(d["property_price"] - 250000) > 0.01 and e.append("property_price not echoed"))

        def n_extra(d, errs, warns):
            if not (3 <= len(d) <= 6):
                warns.append(f"{len(d)} nudges (SPEC: 3-6)")

        self.call("GET nudges", "GET", f"{P}/nudges", L(NUDGE, min_len=1), cust=c, extra=n_extra)

    # ── global routes ──
    def global_suite(self) -> list[str]:
        self.call("GET health", "GET", "/health", HEALTH)
        demo = self.call("GET customers/demo", "GET", "/customers/demo", DEMO)
        if demo:
            ids = {d["customer_id"] for d in demo}
            missing = ALL_DEMO_IDS - ids
            if missing:
                self.results[-1].warnings.append(f"missing demo ids {sorted(missing)}")

        def lesson_loc(d, errs, warns):
            items = d if isinstance(d, list) else d.get("lessons", [])
            if items and "title" not in items[0]:
                warns.append("lessons have no 'title'")

        self.call("GET lessons ?locale=en", "GET", "/lessons", LESSONS, params={"locale": "en"}, extra=lesson_loc)
        self.call("GET lessons ?locale=fi", "GET", "/lessons", LESSONS, params={"locale": "fi"}, extra=lesson_loc)

        def p_extra(d, errs, warns):
            txt = json.dumps(d).lower()
            for p in ("sisu", "aava"):
                if p not in txt:
                    errs.append(f"persona '{p}' missing")

        self.call("GET personas", "GET", "/personas", PERSONAS, extra=p_extra)
        # unknown customer should not 500
        self.call("GET overview (unknown id → 404)", "GET", "/customers/CUST_DOES_NOT_EXIST/overview", None, expect=(404, 422))
        return [d["customer_id"] for d in demo] if demo else []

    # ── SSE chat ──
    def chat(self, cust: str, persona: str, locale: str, question: str, expect_widget: bool) -> str | None:
        name = f"POST chat [{persona}/{locale}] {question[:34]}"
        body = {"customer_id": cust, "persona": persona, "locale": locale,
                "messages": [{"role": "user", "content": question}], "image_base64": None}
        errs: list[str] = []
        warns: list[str] = []
        events: list[tuple[str, Any]] = []
        t0 = time.perf_counter()
        t_first = t_token = None
        try:
            with self.client.stream("POST", self.api + "/chat", json=body, headers={"Accept": "text/event-stream"},
                                    timeout=httpx.Timeout(120.0, connect=10.0)) as r:
                if r.status_code != 200:
                    r.read()
                    errs.append(f"HTTP {r.status_code}: {r.text[:200]}")
                else:
                    ctype = r.headers.get("content-type", "")
                    if "text/event-stream" not in ctype:
                        errs.append(f"content-type {ctype!r} is not text/event-stream")
                    for ev, raw in _iter_sse(r.iter_lines()):
                        now = time.perf_counter()
                        t_first = t_first or now
                        if ev == "token" and t_token is None:
                            t_token = now
                        try:
                            data = json.loads(raw) if raw else None
                        except ValueError:
                            errs.append(f"event {ev}: data is not JSON: {raw[:80]}")
                            continue
                        events.append((ev, data))
                        if ev == "done":
                            break
        except httpx.HTTPError as e:
            errs.append(f"{type(e).__name__}: {e}")
        ms = (time.perf_counter() - t0) * 1000

        kinds = [e for e, _ in events]
        msg_id = None
        if events:
            for i, (ev, data) in enumerate(events):
                spec = SSE_SHAPES.get(ev)
                if spec is None:
                    errs.append(f"unknown event type {ev!r}")
                    continue
                spec.check(data, f"{ev}#{i}", errs)
                if ev == "widget" and isinstance(data, dict):
                    wt = data.get("type")
                    if wt not in WIDGET_TYPES:
                        warns.append(f"unknown widget type {wt!r} (app will ignore it)")
                    elif wt in WIDGET_DATA:
                        WIDGET_DATA[wt].check(data.get("data"), f"widget[{wt}].data", errs)
            if "error" in kinds:
                errs.append(f"error event: {_short(events[kinds.index('error')][1])}")
            if "done" not in kinds:
                errs.append("stream ended without a 'done' event")
            else:
                if kinds.count("done") > 1:
                    errs.append("more than one 'done' event")
                if kinds[-1] != "done":
                    errs.append("'done' is not the last event")
                done = events[kinds.index("done")][1] or {}
                msg_id = done.get("message_id")
                if isinstance(done.get("suggestions"), list) and len(done["suggestions"]) != 3:
                    warns.append(f"{len(done['suggestions'])} suggestions (SPEC: 3)")
                tools_used = [d.get("name") for e, d in events if e == "tool" and isinstance(d, dict)]
                src_tools = (done.get("sources") or {}).get("tools") or []
                if tools_used and not set(tools_used) & set(src_tools):
                    warns.append(f"done.sources.tools {src_tools} doesn't list tools used {tools_used}")
            if kinds and kinds[0] != "status":
                warns.append(f"first event is {kinds[0]!r}, SPEC expects 'status' first")
            if "token" not in kinds:
                errs.append("no 'token' events (empty answer)")
            else:
                first_tok = kinds.index("token")
                last_tok = len(kinds) - 1 - kinds[::-1].index("token")
                # tools must run before the answer starts streaming
                late_tools = [i for i, k in enumerate(kinds) if k == "tool" and i > first_tok]
                if late_tools:
                    warns.append("'tool' event after tokens started")
                if "done" in kinds and kinds.index("done") < last_tok:
                    errs.append("token after done")
                text = "".join(d.get("text", "") for e, d in events if e == "token" and isinstance(d, dict))
                if len(text.strip()) < 10:
                    errs.append(f"answer too short: {text!r}")
                if re.search(r"<think>|</think>", text):
                    errs.append("reasoning/<think> text leaked into answer")
                if locale == "fi" and not re.search(r"[äöÄÖ]|\b(ja|on|sinun|olet|kuluttaja)\b", text):
                    warns.append("locale=fi but answer doesn't look Finnish")
            if expect_widget and "widget" not in kinds:
                warns.append("no widget emitted (expected generative UI for this question)")
            if expect_widget and "tool" not in kinds:
                warns.append("no tool event (expected a data tool call)")
        elif not errs:
            errs.append("no SSE events received")

        ttfe = f"{(t_first - t0) * 1000:.0f}" if t_first else "-"
        ttft = f"{(t_token - t0) * 1000:.0f}" if t_token else "-"
        counts = ",".join(f"{k}:{kinds.count(k)}" for k in ("status", "tool", "widget", "token") if kinds.count(k))
        info = f"first-event {ttfe}ms, first-token {ttft}ms; {counts}"
        self.results.append(Result(name, cust, not errs, ms, errs, warns, info))
        return msg_id

    def feedback(self, cust: str, msg_id: Any) -> None:
        self.call("POST chat/feedback", "POST", "/chat/feedback", FEEDBACK_ANY, cust=cust,
                  body={"message_id": msg_id, "rating": 1, "comment": "e2e smoke"}, expect=(200, 201, 202, 204))


def _iter_sse(lines):
    """Yield (event, data) from an SSE line iterator (handles multi-line data and comments)."""
    ev, data = "message", []
    for line in lines:
        line = line.rstrip("\r")
        if line == "":
            if data:
                yield ev, "\n".join(data)
            ev, data = "message", []
        elif line.startswith(":"):
            continue
        elif line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            data.append(line[5:].lstrip(" ") if line.startswith("data: ") else line[5:])
    if data:
        yield ev, "\n".join(data)


def _info(d: Any) -> str:
    if isinstance(d, list):
        return f"{len(d)} items"
    if isinstance(d, dict):
        for k in ("total_count", "safe_per_day", "total", "status", "verdict", "feasibility", "risk"):
            if k in d and not isinstance(d[k], (dict, list)):
                return f"{k}={d[k]}"
        if "archetype" in d and isinstance(d["archetype"], dict):
            return f"archetype={d['archetype'].get('key')}"
        return f"{len(d)} keys"
    return ""


def print_table(results: list[Result], verbose: bool) -> tuple[int, int, int]:
    use_color = sys.stdout.isatty()
    col = (lambda c, s: f"\033[{c}m{s}\033[0m") if use_color else (lambda c, s: s)
    w = max(len(r.name) for r in results) if results else 20
    w = min(max(w, 20), 60)
    print()
    print(f"{'':4} {'check':<{w}}  {'customer':<10} {'ms':>7}  notes")
    print("─" * (w + 40))
    npass = nfail = nwarn = 0
    for r in results:
        if not r.ok:
            tag, nfail = col("31", "FAIL"), nfail + 1
        elif r.warnings:
            tag, nwarn = col("33", "WARN"), nwarn + 1
        else:
            tag = col("32", "PASS")
        if r.ok:
            npass += 1
        note = r.info
        print(f"{tag} {r.name[:w]:<{w}}  {r.customer:<10} {r.ms:7.0f}  {note}")
        for e in r.errors[: (50 if verbose else 6)]:
            print(f"     {col('31', '✘')} {e}")
        if len(r.errors) > 6 and not verbose:
            print(f"     … {len(r.errors) - 6} more (use -v)")
        for wmsg in r.warnings:
            print(f"     {col('33', '!')} {wmsg}")
    print("─" * (w + 40))
    rest = [r.ms for r in results if r.ok and not r.name.startswith("POST chat ")]
    if rest:
        rest.sort()
        p50 = rest[len(rest) // 2]
        p95 = rest[min(len(rest) - 1, int(len(rest) * 0.95))]
        print(f"REST latency: p50 {p50:.0f} ms · p95 {p95:.0f} ms · max {rest[-1]:.0f} ms  ({len(rest)} calls)")
    summary = f"{npass} passed ({nwarn} with warnings), {nfail} failed, {len(results)} checks"
    print(col("32" if nfail == 0 else "31", summary))
    return npass, nfail, nwarn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8000", help="backend base URL (without /api)")
    ap.add_argument("--customers", default=",".join(DEFAULT_CUSTOMERS), help="comma-separated customer ids")
    ap.add_argument("--skip-chat", action="store_true", help="skip POST /api/chat SSE checks")
    ap.add_argument("--timeout", type=float, default=30.0, help="REST timeout seconds")
    ap.add_argument("--slow-ms", type=float, default=1500.0, help="warn when a REST call is slower than this")
    ap.add_argument("--json", metavar="PATH", help="also write the results as JSON")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()

    s = Smoke(a.base, a.timeout, a.slow_ms)
    print(f"SPankkiBot API smoke → {s.api}")
    try:
        s.client.get(s.api + "/health", timeout=5)
    except httpx.HTTPError as e:
        print(f"✘ backend not reachable at {a.base}: {e}\n  start it with: scripts/dev.sh --backend-only")
        return 2

    s.global_suite()
    customers = [c.strip() for c in a.customers.split(",") if c.strip()]
    for c in customers:
        s.customer_suite(c)

    if not a.skip_chat:
        msg_ids = []
        for i, (persona, locale, q, w) in enumerate(CHAT_QUESTIONS):
            cust = customers[i % len(customers)]
            mid = s.chat(cust, persona, locale, q, w)
            if mid is not None:
                msg_ids.append((cust, mid))
        if msg_ids:
            s.feedback(*msg_ids[0])
        else:
            s.results.append(Result("POST chat/feedback", "-", False, 0, ["skipped: no message_id from chat"]))

    _, nfail, _ = print_table(s.results, a.verbose)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump([r.__dict__ for r in s.results], f, ensure_ascii=False, indent=2)
        print(f"wrote {a.json}")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
