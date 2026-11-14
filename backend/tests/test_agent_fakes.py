"""Shared fakes for the agent tests (no tests in this module).

``install_fake_analytics(monkeypatch)`` registers in-memory stand-ins for every
``app.analytics.<module>`` the agent calls, via ``sys.modules``. The agent resolves
analytics lazily with ``importlib.import_module``, so the fakes are picked up without
touching DuckDB, the dataset or the real analytics package.

``FakeLLM`` replays scripted rounds of :class:`app.agent.llm.LLMChunk` events.
"""

from __future__ import annotations

import sys
import types
from typing import Any

from app.agent.llm import LLMChunk, ToolCall

CALLS: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []


def _rec(name: str):
    def deco(fn):
        def wrapper(*args, **kwargs):
            CALLS.append((name, args, kwargs))
            return fn(*args, **kwargs)

        return wrapper

    return deco


@_rec("query_spending")
def query_spending(customer_id, start=None, end=None, category=None, basket=None, merchant=None, mcc=None, group_by="none", direction="out", top_n=20):
    groups: list[dict[str, Any]] = []
    if group_by == "category":
        groups = [{"key": "Restaurants", "label": "Restaurants", "total": 120.5, "count": 6}, {"key": "Groceries", "label": "Groceries", "total": 80.0, "count": 4}, {"key": "Transportation", "label": "Transportation", "total": 40.0, "count": 2}]
    elif group_by == "month":
        groups = [{"key": "2026-08", "label": "Aug 2026", "total": 90.0, "count": 3}, {"key": "2026-07", "label": "Jul 2026", "total": 60.0, "count": 2}]
    elif group_by == "merchant":
        groups = [{"key": f"MRC-RES-{i:04d}", "label": f"Restaurant #{i}", "total": 50.0 - i, "count": 2} for i in range(1, 9)]
    total = 64.2 if mcc == 4121 else 240.5
    return {"filters": {}, "total": total, "count": 4 if mcc == 4121 else 12, "avg_tx": 16.05, "groups": groups, "period": {"start": start or "2026-06-20", "end": end or "2026-09-18"}}


@_rec("search_transactions")
def search_transactions(customer_id, start=None, end=None, category=None, basket=None, merchant=None, min_amount=None, max_amount=None, text=None, limit=50, offset=0):
    items = [
        {"id": "tx_1", "date": "2026-09-10", "timestamp": "2026-09-10T20:00:00", "amount": -25.0, "category": "Transportation", "basket": "leak", "merchant_id": "MRC-TRN-0003", "merchant_label": "Taxi #3", "mcc": 4121, "mcc_label": "Taxi", "icon": "🚕", "balance_after": 500.0, "type": "purchase"},
        {"id": "tx_2", "date": "2026-09-05", "timestamp": "2026-09-05T08:00:00", "amount": -3.2, "category": "Transportation", "basket": "fixed", "merchant_id": "MRC-TRN-0007", "merchant_label": "Public transport #7", "mcc": 4111, "mcc_label": "Transit", "icon": "🚌", "balance_after": 525.0, "type": "purchase"},
        {"id": "tx_3", "date": "2026-09-01", "timestamp": "2026-09-01T09:00:00", "amount": 2100.0, "category": "Salary", "basket": "income", "merchant_id": None, "merchant_label": "Salary", "mcc": None, "mcc_label": None, "icon": "💶", "balance_after": 528.2, "type": "salary"},
    ]
    return {"items": items[:limit], "total_count": len(items)}


@_rec("get_overview")
def get_overview(customer_id):
    return {
        "customer": {"id": customer_id, "name": "Emma", "age": 21, "postal_code": "00100"},
        "as_of": "2026-09-18",
        "balance": 512.3,
        "trend_30d": [],
        "month": {"income": 900.0, "spent": 640.0, "saved": 50.0, "by_basket": {"fixed": 400.0, "irregular": 40.0, "leak": 200.0}},
        "safe_to_spend": safe_to_spend(customer_id),
        "recovery": recovery(customer_id),
        "goals": list_goals(customer_id),
        "recent_transactions": [],
        "nudges": [{"id": "n1", "kind": "tip", "text": "Leaks are up", "emoji": "💧", "action_prompt": "Show leaks"}],
    }


def recovery(customer_id, sts=None):
    return {"state": "ordinary", "months": 6, "balance": 512.3, "monthly_income": 900.0, "monthly_spending": 640.0,
            "monthly_surplus": 260.0, "deficit": 0.0, "goal_monthly_need": 50.0, "planned_monthly_change": None,
            "urgency": "comfortable", "safe_per_day": 23.0, "days_until_payday": 7, "goal_contributions": 20.0,
            "goal_reservations_present": True, "tx_count": 24, "period": "2026-03-01..2026-08-31"}


def safe_to_spend(customer_id):
    status = "critical" if customer_id == "CRIT" else "comfortable"
    return {"balance": 512.3, "next_payday": "2026-09-25", "days_until_payday": 7, "upcoming_bills": [{"label": "Phone", "amount": 19.9, "expected_date": "2026-09-20"}], "irregular_buffer": 30.0, "goal_contributions": 20.0, "safe_total": 161.0, "safe_per_day": 23.0, "safe_this_week": 161.0, "status": status, "explanation": "..."}


def get_baskets(customer_id, months=6):
    return {
        "months": [{"month": m, "fixed": 400.0, "irregular": 40.0, "leak": 200.0, "income": 900.0, "saving": 50.0} for m in ("2026-07", "2026-08", "2026-09")],
        "current_month": {"month": "2026-09", "fixed": 400.0, "irregular": 40.0, "leak": 200.0, "income": 900.0, "saving": 50.0, "top": {"fixed": [{"label": "Rent", "total": 350.0}], "irregular": [{"label": "Pharmacy", "total": 40.0}], "leak": [{"label": "Café #12", "total": 60.0}]}},
        "explanations": {"fixed": "Must-pay regular costs", "irregular": "Must-pay but lumpy", "leak": "Small optional purchases"},
    }


def recurring_payments(customer_id):
    return {"items": [{"label": "Streaming", "category": "Entertainment", "merchant_id": None, "avg_amount": 12.99, "cadence": "monthly", "day_of_month": 3, "last_date": "2026-09-03", "basket": "fixed"}], "monthly_total": 12.99}


def spender_profile(customer_id):
    return {"archetype": {"key": "latte_leaker", "name": "Latte Leaker", "emoji": "☕", "description": "Small purchases add up."}, "traits": [], "savings_rate": 0.06, "leak_share": 0.31, "weekend_share": 0.45, "small_tx_per_week": 6.5, "late_night_share": 0.1, "volatility": 0.2}


def benchmarks(customer_id):
    return {"peer_group": {"label": "Age 18–29 in dataset", "size": 700}, "categories": [{"category": "Restaurants", "you_monthly": 120.0, "peer_median_monthly": 80.0, "peer_p25": 50.0, "peer_p75": 110.0, "percentile": 82, "stat_fi_monthly": 70.0}], "income": {}, "savings_rate": {}, "sources": [{"name": "Statistics Finland", "url": "https://stat.fi", "note": ""}]}


@_rec("simulate_what_if")
def simulate_what_if(customer_id, adjustments, horizon_months=12, invest_return_pct=0.0):
    return {"baseline_monthly": 200.0, "new_monthly": 160.0, "monthly_saving": 40.0, "horizon_months": horizon_months, "total_saving": 40.0 * horizon_months, "with_return": 40.0 * horizon_months, "per_item": [], "series": [{"month": 1, "cumulative": 40.0}]}


def list_goals(customer_id):
    return [{"id": "g1", "name": "Emergency fund", "emoji": "🛟", "kind": "emergency", "target_amount": 1000.0, "saved_amount": 300.0, "deadline": None, "monthly_contribution": 50.0, "progress": 0.3, "created_at": "2026-01-01"}]


@_rec("create_goal")
def create_goal(customer_id, name, target_amount, deadline=None, emoji=None, kind="other", saved_amount=0.0):
    return {"id": "g_new", "name": name, "emoji": emoji, "kind": kind, "target_amount": target_amount, "saved_amount": saved_amount, "deadline": deadline, "monthly_contribution": 0.0, "progress": 0.0, "created_at": "2026-09-18"}


@_rec("update_goal")
def update_goal(customer_id, goal_id, **fields):
    return {"id": goal_id, **fields}


def delete_goal(customer_id, goal_id):
    return {"ok": True}


@_rec("plan_goal")
def plan_goal(customer_id, target_amount, deadline=None, name=None, saved_amount=0.0):
    feas = "on_track" if target_amount <= 1000 else "stretch"
    return {"name": name, "target_amount": target_amount, "saved_amount": saved_amount, "deadline": deadline or "2027-06-30", "months": 9, "needed_per_month": round(target_amount / 9, 2), "current_monthly_surplus": 150.0, "gap": 50.0, "feasibility": feas, "suggested_deadline": "2027-12-31", "cuts": [{"label": "Restaurants", "category": "Restaurants", "basket": "leak", "current_monthly": 120.0, "cut_pct": 30, "monthly_saving": 36.0, "why": "..."}], "cuts_total": 36.0, "summary": "..."}


def survival_plan(customer_id, amount=None, until=None):
    return {"amount": amount or 512.3, "until": until or "2026-09-25", "days": 7, "upcoming_bills_total": 19.9, "bills": [], "free_money": 280.1, "per_day": 40.01, "per_week": 280.1, "category_budgets": [{"category": "Groceries", "budget": 100.0, "typical": 120.0}], "risk": "short" if (amount or 0) < 100 else "tight", "shortfall": 0.0, "tips": ["Cook at home"]}


def home_readiness(customer_id, property_price=None):
    return {"property_price": property_price or 200000.0, "loan_needed": 180000.0, "equity_needed": 20000.0, "your_equity_estimate": 5000.0, "required_monthly_income": 3500.0, "your_monthly_income": 2500.0, "ltv": 0.9, "verdict": "not_yet", "gaps": ["Save more"], "dataset_note": "", "customer_application": None}


MODULES = {
    "query": {"query_spending": query_spending, "search_transactions": search_transactions},
    "overview": {"get_overview": get_overview},
    "safe_to_spend": {"safe_to_spend": safe_to_spend},
    "baskets": {"get_baskets": get_baskets},
    "recurring": {"recurring_payments": recurring_payments},
    "profile": {"spender_profile": spender_profile},
    "benchmarks": {"benchmarks": benchmarks},
    "whatif": {"simulate_what_if": simulate_what_if},
    "goals": {"list_goals": list_goals, "create_goal": create_goal, "update_goal": update_goal, "delete_goal": delete_goal, "plan_goal": plan_goal},
    "survival": {"survival_plan": survival_plan},
    "mortgage": {"home_readiness": home_readiness},
    "recovery": {"recovery": recovery},
}


def install_fake_analytics(monkeypatch) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
    """Register fake ``app.analytics.*`` modules; returns the shared call log."""
    import app.analytics

    CALLS.clear()
    for name, funcs in MODULES.items():
        mod = types.ModuleType(f"app.analytics.{name}")
        for fname, fn in funcs.items():
            setattr(mod, fname, fn)
        monkeypatch.setitem(sys.modules, f"app.analytics.{name}", mod)
        monkeypatch.setattr(app.analytics, name, mod, raising=False)
    from app.agent import prompts

    prompts._CACHE.clear()
    return CALLS


class FakeLLM:
    """Replays scripted rounds. Each round is a list of LLMChunk; an Exception instance raises."""

    configured = True

    def __init__(self, rounds: list[list[LLMChunk] | Exception]):
        self.rounds = list(rounds)
        self.calls: list[dict[str, Any]] = []

    def any_healthy(self) -> bool:
        return True

    async def stream(self, messages, tools=None, *, tool_choice=None, temperature=0.4, max_tokens=2048, thinking=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tool_choice": tool_choice, "thinking": thinking})
        if not self.rounds:
            yield LLMChunk(kind="content", text="ok")
            yield LLMChunk(kind="done", finish_reason="stop")
            return
        step = self.rounds.pop(0)
        if isinstance(step, Exception):
            raise step
        for chunk in step:
            yield chunk


def tool_round(name: str, arguments: str, call_id: str = "call_1") -> list[LLMChunk]:
    return [LLMChunk(kind="reasoning"), LLMChunk(kind="tool_calls", tool_calls=[ToolCall(call_id, name, arguments)], finish_reason="tool_calls"), LLMChunk(kind="done", finish_reason="tool_calls")]


def text_round(*parts: str) -> list[LLMChunk]:
    return [LLMChunk(kind="content", text=p) for p in parts] + [LLMChunk(kind="done", finish_reason="stop")]
