"""Tool executors: schemas, widget mapping (SPEC §5.3), consent for writes, provenance."""

from __future__ import annotations

from datetime import date

import pytest

from app.agent.tools import TOOL_NAMES, TOOL_SCHEMAS, ToolContext, execute_tool, find_lesson, status_label, user_confirmed
from tests.test_agent_fakes import install_fake_analytics

SPEC_TOOLS = {
    "get_overview", "query_spending", "search_transactions", "get_baskets", "safe_to_spend", "recurring_payments",
    "spender_profile", "benchmarks", "simulate_what_if", "list_goals", "plan_goal", "create_goal", "update_goal",
    "survival_plan", "home_readiness", "explain_concept", "render_chart",
}
WIDGET_TYPES = {"kpi", "bar_chart", "line_chart", "donut_chart", "basket_breakdown", "safe_to_spend", "goal_plan", "what_if", "transaction_list", "spender_profile", "benchmark", "survival_plan", "home_readiness", "lesson", "action_buttons"}


@pytest.fixture
def ctx(monkeypatch) -> ToolContext:
    install_fake_analytics(monkeypatch)
    return ToolContext(customer_id="CUST05020", locale="en", persona="sisu", as_of=date(2026, 9, 18))


def test_every_spec_tool_has_a_valid_schema():
    assert set(TOOL_NAMES) == SPEC_TOOLS
    for schema in TOOL_SCHEMAS:
        fn = schema["function"]
        assert schema["type"] == "function" and fn["description"]
        assert fn["parameters"]["type"] == "object"
        for req in fn["parameters"]["required"]:
            assert req in fn["parameters"]["properties"]
    qs = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "query_spending")["function"]["parameters"]["properties"]
    assert "Restaurants" in qs["category"]["enum"] and "leak" in qs["basket"]["enum"] and "month" in qs["group_by"]["enum"]


def _types(result) -> list[str]:
    return [w["type"] for w in result.widgets]


@pytest.mark.parametrize(
    "name,args,expected",
    [
        ("query_spending", {"period": "this_month"}, ["kpi"]),
        ("query_spending", {"group_by": "category"}, ["donut_chart"]),
        ("query_spending", {"group_by": "merchant"}, ["bar_chart"]),
        ("query_spending", {"group_by": "month", "period": "last_6_months"}, ["line_chart"]),
        ("search_transactions", {"subcategory": "taxi"}, ["transaction_list"]),
        ("get_baskets", {}, ["basket_breakdown", "line_chart"]),
        ("safe_to_spend", {}, ["safe_to_spend"]),
        ("spender_profile", {}, ["spender_profile"]),
        ("benchmarks", {}, ["benchmark"]),
        ("simulate_what_if", {"adjustments": [{"category": "Restaurants", "change_pct": -20}]}, ["what_if"]),
        ("plan_goal", {"target_amount": 12000, "name": "Car"}, ["goal_plan", "action_buttons"]),
        ("survival_plan", {"amount": 300}, ["survival_plan"]),
        ("home_readiness", {}, ["home_readiness"]),
        ("explain_concept", {"topic": "three baskets"}, ["lesson"]),
        ("render_chart", {"title": "T", "chart_type": "line", "data": [{"label": "a", "value": 1}]}, ["line_chart"]),
        ("recurring_payments", {}, ["kpi", "bar_chart"]),
        ("get_overview", {}, ["kpi", "donut_chart"]),
    ],
)
async def test_widget_mapping(ctx, name, args, expected):
    result = await execute_tool(name, args, ctx)
    assert result.error is None, result.llm_payload
    assert _types(result) == expected
    for w in result.widgets:
        assert w["type"] in WIDGET_TYPES and w["id"].startswith("w_") and isinstance(w["data"], dict)


async def test_taxi_subcategory_maps_to_mcc_and_last_month(ctx):
    calls = install_fake_analytics(__import__("pytest").MonkeyPatch())  # fresh log
    result = await execute_tool("query_spending", {"subcategory": "taxi", "period": "last_month"}, ctx)
    q = next(c for c in calls if c[0] == "query_spending" and c[2].get("mcc") == 4121)
    assert q[2]["category"] == "Transportation" and q[2]["start"] == "2026-08-01" and q[2]["end"] == "2026-08-31"
    assert result.llm_payload["total"] == 64.2 and result.sources["period"] == "Aug 2026" and result.sources["tx_count"] == 4


async def test_multi_mcc_subcategory_is_merged(ctx):
    result = await execute_tool("query_spending", {"subcategory": "fuel"}, ctx)
    assert result.llm_payload["total"] == pytest.approx(481.0)  # 2 × 240.5
    assert result.llm_payload["count"] == 24


async def test_what_if_slider_config(ctx):
    result = await execute_tool("simulate_what_if", {"adjustments": [{"category": "dining out", "change_pct": -20}]}, ctx)
    data = result.widgets[0]["data"]
    assert data["slider"] == {"category": "Restaurants", "min": -100, "max": 0, "value": -20.0}
    assert data["result"]["monthly_saving"] == 40.0


async def test_plan_goal_proposes_create_button(ctx):
    result = await execute_tool("plan_goal", {"target_amount": 12000, "name": "Car", "deadline": "2027-06"}, ctx)
    buttons = result.widgets[1]["data"]["buttons"]
    assert buttons[0]["kind"] == "create_goal"
    assert buttons[0]["payload"] == {"name": "Car", "target_amount": 12000.0, "deadline": "2027-06-30", "emoji": "🚗", "kind": "car", "saved_amount": 0.0}
    assert "Create goal 'Car'" in buttons[0]["label"]


async def test_create_goal_requires_confirmation(ctx):
    calls = install_fake_analytics(__import__("pytest").MonkeyPatch())
    ctx.user_text = "Help me save for a car"
    result = await execute_tool("create_goal", {"name": "Car", "target_amount": 12000}, ctx)
    assert result.llm_payload["status"] == "proposed_not_saved"
    assert _types(result) == ["action_buttons"]
    assert not any(c[0] == "create_goal" for c in calls)
    ctx.user_text = "Yes, create it"
    result = await execute_tool("create_goal", {"name": "Car", "target_amount": 12000}, ctx)
    assert result.llm_payload["status"] == "saved"
    assert any(c[0] == "create_goal" for c in calls)


async def test_update_goal_requires_confirmation(ctx):
    ctx.user_text = "maybe later"
    result = await execute_tool("update_goal", {"goal_id": "g1", "target_amount": 900}, ctx)
    assert result.llm_payload["status"] == "proposed_not_saved"


@pytest.mark.parametrize("text,ok", [("yes please", True), ("Kyllä, luo tavoite", True), ("create a goal for a trip", True), ("how much do I spend?", False), ("joo", True)])
def test_user_confirmed(text, ok):
    assert user_confirmed(text) is ok


async def test_errors_become_payloads_not_exceptions(ctx):
    bad = await execute_tool("plan_goal", {"target_amount": -5}, ctx)
    assert bad.error == "invalid_arguments" and "target_amount" in bad.llm_payload["error"]
    unknown = await execute_tool("nope", {}, ctx)
    assert unknown.error == "unknown_tool"
    empty_chart = await execute_tool("render_chart", {"title": "x", "chart_type": "bar", "data": []}, ctx)
    assert empty_chart.error == "invalid_arguments"


async def test_analytics_failure_is_contained(ctx, monkeypatch):
    import sys

    def boom(customer_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(sys.modules["app.analytics.profile"], "spender_profile", boom)
    result = await execute_tool("spender_profile", {}, ctx)
    assert result.error == "tool_failed" and "temporarily unavailable" in result.llm_payload["error"]


async def test_llm_payload_is_compact_aggregate(ctx):
    result = await execute_tool("search_transactions", {"limit": 20}, ctx)
    # the model sees at most 10 slim rows; the widget gets full Tx objects
    assert all(set(i) <= {"date", "amount", "label", "category", "basket"} for i in result.llm_payload["items"])
    assert "merchant_id" in result.widgets[0]["data"]["items"][0]


async def test_largest_purchases_exclude_income(ctx):
    result = await execute_tool("search_transactions", {"sort": "largest"}, ctx)
    amounts = [t["amount"] for t in result.widgets[0]["data"]["items"]]
    assert amounts == sorted(amounts) and all(a < 0 for a in amounts)


@pytest.mark.parametrize(
    "name,args,locale,persona,expected",
    [
        ("query_spending", {"category": "Restaurants"}, "en", "sisu", "Checking your restaurant spending…"),
        ("query_spending", {"category": "Restaurants"}, "fi", "aava", "Tarkistan ravintolakulujasi…"),
        ("query_spending", {"subcategory": "taxi"}, "fi", "sisu", "Tarkistan taksikulujasi…"),
        ("spender_profile", {}, "en", "sisu", "Running your spender fitness test…"),
        ("spender_profile", {}, "en", "aava", "Reading your spending habits…"),
    ],
)
def test_status_labels(name, args, locale, persona, expected):
    assert status_label(name, args, locale, persona) == expected


def test_lessons_fallback_and_quiz_shape():
    lesson = find_lesson("emergency buffer", "fi")
    assert lesson["title"] and lesson["body"] and lesson["emoji"]
    if "quiz" in lesson:
        q = lesson["quiz"]
        assert 0 <= q["answer_index"] < len(q["options"])
