"""Customer-scoped REST endpoints (SPEC §3.2): ``/api/customers/...``.

Every handler is a plain ``def`` so FastAPI runs it in its thread pool (DuckDB is
synchronous) and maps 1:1 to an analytics function documented in :mod:`app.analytics`.
Unknown customers raise :class:`app.db.CustomerNotFound`, turned into HTTP 404 by the
exception handlers in :mod:`app.main`; invalid arguments raise ``ValueError`` → 422.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Query

from app import db
from app.analytics import (
    baskets,
    benchmarks,
    goals,
    mortgage,
    nudges,
    overview,
    profile,
    query,
    recurring,
    safe_to_spend,
    survival,
    whatif,
)
from app.demo import DEMO_CUSTOMERS, tagline
from app.routers.deps import (
    CustomerId,
    GoalCreate,
    GoalPlanRequest,
    GoalUpdate,
    WhatIfRequest,
    require_customer,
)

async def _locale_param(
    locale: str | None = Query(None, description="en | fi | sv for texts and labels (unknown → en)"),
) -> None:
    """Documents ``?locale=`` on every route; :class:`app.i18n.LocaleMiddleware` applies it."""


router = APIRouter(prefix="/customers", tags=["customers"], dependencies=[Depends(_locale_param)])

GroupBy = Literal["none", "category", "basket", "month", "week", "weekday", "merchant", "hour", "day"]
Basket = Literal["fixed", "irregular", "leak", "income", "saving"]


@router.get("/demo", summary="Demo customers for the persona picker")
def demo_customers() -> list[dict[str, Any]]:
    out = []
    for cid, meta in DEMO_CUSTOMERS.items():
        c = db.get_customer(cid)
        out.append({"customer_id": cid, "name": meta["name"], "age": c["age"],
                    "postal_code": c["postal_code"], "tagline": tagline(cid),
                    "avatar_emoji": meta["avatar_emoji"]})
    return out


@router.get("/{customer_id}/overview", summary="Everything for the home screen in one call")
def get_overview(customer_id: CustomerId) -> dict[str, Any]:
    return overview.get_overview(customer_id)


@router.get("/{customer_id}/balance", summary="Current balance and 30-day trend")
def get_balance(customer_id: CustomerId) -> dict[str, Any]:
    require_customer(customer_id)
    return overview.get_balance(customer_id)


@router.get("/{customer_id}/transactions", summary="Search transactions (newest first)")
def get_transactions(
    customer_id: CustomerId,
    start: str | None = Query(None, description="YYYY-MM-DD"),
    end: str | None = Query(None, description="YYYY-MM-DD"),
    category: str | None = Query(None, description="Category name, comma-separated for several"),
    basket: Basket | None = None,
    merchant: str | None = Query(None, description="Merchant id, e.g. MRC-RES-0038"),
    min_amount: float | None = Query(None, ge=0),
    max_amount: float | None = Query(None, ge=0),
    text: str | None = Query(None, max_length=60),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1_000_000),
) -> dict[str, Any]:
    return query.search_transactions(customer_id, start, end, category, basket, merchant,
                                     min_amount, max_amount, text, limit, offset)


@router.get("/{customer_id}/spending", summary="Aggregate spending (MyData engine)")
def get_spending(
    customer_id: CustomerId,
    start: str | None = Query(None, description="YYYY-MM-DD (default: 90 days before as-of)"),
    end: str | None = Query(None, description="YYYY-MM-DD (default: as-of)"),
    category: str | None = None,
    basket: Basket | None = None,
    merchant: str | None = None,
    mcc: int | None = None,
    group_by: GroupBy = "none",
    direction: Literal["out", "in", "all"] = "out",
    top_n: int = Query(20, ge=1, le=400),
) -> dict[str, Any]:
    return query.query_spending(customer_id, start, end, category, basket, merchant, mcc,
                                group_by, direction, top_n)


@router.get("/{customer_id}/baskets", summary="Three-basket split per month")
def get_baskets(customer_id: CustomerId, months: int = Query(6, ge=1, le=24)) -> dict[str, Any]:
    return baskets.get_baskets(customer_id, months)


@router.get("/{customer_id}/safe-to-spend", summary="Safe to spend until next payday")
def get_safe_to_spend(customer_id: CustomerId) -> dict[str, Any]:
    return safe_to_spend.safe_to_spend(customer_id)


@router.get("/{customer_id}/recurring", summary="Detected bills and subscriptions")
def get_recurring(customer_id: CustomerId) -> dict[str, Any]:
    return recurring.recurring_payments(customer_id)


@router.get("/{customer_id}/profile", summary="Spender archetype with transparent traits")
def get_profile(customer_id: CustomerId) -> dict[str, Any]:
    return profile.spender_profile(customer_id)


@router.get("/{customer_id}/benchmarks", summary="Compare with peers and Statistics Finland")
def get_benchmarks(customer_id: CustomerId) -> dict[str, Any]:
    return benchmarks.benchmarks(customer_id)


@router.post("/{customer_id}/what-if", summary="Simulate spending changes")
def post_what_if(customer_id: CustomerId, body: WhatIfRequest) -> dict[str, Any]:
    return whatif.simulate_what_if(customer_id, [a.model_dump(exclude_none=True) for a in body.adjustments],
                                   body.horizon_months, body.invest_return_pct)


@router.get("/{customer_id}/goals", summary="List savings goals")
def get_goals(customer_id: CustomerId) -> list[dict[str, Any]]:
    return goals.list_goals(customer_id)


@router.post("/{customer_id}/goals", status_code=201, summary="Create a savings goal")
def post_goal(customer_id: CustomerId, body: GoalCreate) -> dict[str, Any]:
    return goals.create_goal(customer_id, body.name, body.target_amount, body.deadline, body.emoji,
                             body.kind, body.saved_amount)


@router.post("/{customer_id}/goals/plan", summary="Plan a goal against your real surplus")
def post_goal_plan(customer_id: CustomerId, body: GoalPlanRequest) -> dict[str, Any]:
    return goals.plan_goal(customer_id, body.target_amount, body.deadline, body.name, body.saved_amount)


@router.patch("/{customer_id}/goals/{goal_id}", summary="Update a goal")
def patch_goal(customer_id: CustomerId, goal_id: str, body: GoalUpdate) -> dict[str, Any]:
    return goals.update_goal(customer_id, goal_id, **body.fields())


@router.delete("/{customer_id}/goals/{goal_id}", summary="Delete a goal")
def delete_goal(customer_id: CustomerId, goal_id: str) -> dict[str, Any]:
    return goals.delete_goal(customer_id, goal_id)


@router.get("/{customer_id}/survival", summary="Daily survival budget until a date")
def get_survival(
    customer_id: CustomerId,
    amount: float | None = Query(None, ge=0, le=1_000_000,
                                 description="Money to live on (default: current balance minus bills)"),
    until: str | None = Query(None, description="YYYY-MM-DD (default: next payday)"),
) -> dict[str, Any]:
    return survival.survival_plan(customer_id, amount, until)


@router.get("/{customer_id}/home-readiness", summary="Mortgage readiness check")
def get_home_readiness(
    customer_id: CustomerId,
    property_price: float | None = Query(None, gt=0, le=10_000_000),
) -> dict[str, Any]:
    return mortgage.home_readiness(customer_id, property_price)


@router.get("/{customer_id}/nudges", summary="Proactive tips for the character bubble")
def get_nudges(customer_id: CustomerId) -> list[dict[str, Any]]:
    return nudges.nudges(customer_id)
