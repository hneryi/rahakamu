"""Offline fallback: intent routing (en + fi), parsing, templated answers, grounding check."""

from __future__ import annotations

from datetime import date

import pytest

from app.agent.evals.grounding import check_grounding, extract_numbers
from app.agent.events import ChatRequest
from app.agent.fallback import compose_answer, parse_amounts, parse_deadline, parse_percent, parse_period, route
from app.agent.personas import get_persona
from app.agent.tools import ToolContext, execute_tool
from tests.test_agent_fakes import install_fake_analytics

AS_OF = date(2026, 9, 18)

CHALLENGE_QUESTIONS = [
    ("How much did I spend on taxis last month?", "en", "query_spending", {"subcategory": "taxi", "period": "last_month"}),
    ("What kind of spender am I?", "en", "spender_profile", {}),
    ("What is safe for me to spend this week?", "en", "safe_to_spend", {}),
    ("How much could I save if I reduced dining out by 20%?", "en", "simulate_what_if", {"adjustments": [{"change_pct": -20.0, "category": "Restaurants"}], "horizon_months": 12}),
    ("Help me save for a car that costs 12000", "en", "plan_goal", {"target_amount": 12000.0, "name": "Car"}),
    ("How do I survive this month with 300 €?", "en", "survival_plan", {"amount": 300.0}),
    ("Paljonko käytin takseihin viime kuussa?", "fi", "query_spending", {"subcategory": "taxi", "period": "last_month"}),
    ("Millainen kuluttaja olen?", "fi", "spender_profile", {}),
    ("Paljonko voin turvallisesti käyttää tällä viikolla?", "fi", "safe_to_spend", {}),
    ("Paljonko säästäisin, jos vähentäisin ulkona syömistä 20 %?", "fi", "simulate_what_if", {"adjustments": [{"change_pct": -20.0, "category": "Restaurants"}], "horizon_months": 12}),
    ("Auta minua säästämään 12000 € autoon", "fi", "plan_goal", {"target_amount": 12000.0, "name": "Auto"}),
    ("Miten selviän tästä kuusta 300 eurolla?", "fi", "survival_plan", {"amount": 300.0}),
]


@pytest.mark.parametrize("text,locale,tool,args", CHALLENGE_QUESTIONS)
def test_challenge_questions_route_to_the_right_tool(text, locale, tool, args):
    intent = route(text, locale, AS_OF)
    assert intent.calls[0] == (tool, args)


@pytest.mark.parametrize(
    "text,tool",
    [
        ("Am I spending more than people my age?", "benchmarks"),
        ("Kulutanko enemmän kuin ikätoverini?", "benchmarks"),
        ("Show my subscriptions", "recurring_payments"),
        ("Mitä tilauksia minulla on?", "recurring_payments"),
        ("Explain the three money baskets with my own numbers", "get_baskets"),
        ("What is compound interest?", "explain_concept"),
        ("Mikä on puskurirahasto?", "explain_concept"),
        ("Voinko ostaa asunnon?", "home_readiness"),
        ("Can I afford a 250 000 € apartment?", "home_readiness"),
        ("Can I afford a 250 € concert this weekend?", "safe_to_spend"),
        ("Can I afford a 12 000 € car?", "plan_goal"),
        ("Show my biggest purchases last month", "search_transactions"),
        ("How much do I spend on groceries per month?", "query_spending"),
        ("Kerro saldoni", "get_overview"),
        ("Hi", "get_overview"),
        ("Show my goals", "list_goals"),
    ],
)
def test_more_intents(text, tool):
    assert route(text, "fi" if any(ch in text for ch in "äö") else "en", AS_OF).calls[0][0] == tool


def test_confirm_create_uses_previous_message():
    intent = route("Yes, create this goal", "en", AS_OF, history=["Help me save for a car that costs 12000 by June"])
    name, args = intent.calls[0]
    assert name == "create_goal" and args["target_amount"] == 12000 and args["deadline"] == "2027-06-30" and args["kind"] == "car"


@pytest.mark.parametrize(
    "text,expected",
    [("12000", [12000.0]), ("12 000 €", [12000.0]), ("12k", [12000.0]), ("300 euroa", [300.0]), ("1,500.50 €", [1500.5]), ("20 % in 2027", []), ("in 3 months", []), ("by 2027-06 save 5000", [5000.0])],
)
def test_parse_amounts(text, expected):
    assert parse_amounts(text) == expected


def test_parse_percent_deadline_period():
    assert parse_percent("cut by 25 prosenttia") == 25.0
    assert parse_deadline("by June", AS_OF) == "2027-06-30"
    assert parse_deadline("by December", AS_OF) == "2026-12-31"
    assert parse_deadline("kesäkuuhun 2028 mennessä", AS_OF) == "2028-06-30"
    assert parse_deadline("in 18 months", AS_OF) == "2028-03-18"
    assert parse_deadline("vuodessa", AS_OF) == "2027-09-18"
    assert parse_period("elokuussa", AS_OF) == {"start": "2026-08-01", "end": "2026-08-31"}
    assert parse_period("in October", AS_OF) == {"start": "2025-10-01", "end": "2025-10-31"}
    assert parse_period("viime viikolla", AS_OF) == {"period": "last_week"}


@pytest.mark.parametrize("persona,locale", [("sisu", "en"), ("aava", "en"), ("sisu", "fi"), ("aava", "fi")])
async def test_templates_are_grounded_and_in_persona(monkeypatch, persona, locale):
    install_fake_analytics(monkeypatch)
    ctx = ToolContext(customer_id="CUST05020", locale=locale, persona=persona, as_of=AS_OF)
    p = get_persona(persona)
    for name, args in [("safe_to_spend", {}), ("plan_goal", {"target_amount": 12000, "name": "Car"}), ("simulate_what_if", {"adjustments": [{"category": "Restaurants", "change_pct": -20}]}), ("query_spending", {"subcategory": "taxi", "period": "last_month"}), ("survival_plan", {"amount": 300}), ("spender_profile", {}), ("get_baskets", {}), ("benchmarks", {}), ("home_readiness", {}), ("recurring_payments", {}), ("get_overview", {})]:
        res = await execute_tool(name, args, ctx)
        text = compose_answer([(name, res)], p, locale)
        assert text.strip()
        report = check_grounding(text, [res.llm_payload, res.raw], locale=locale)
        assert report.ok, (name, report.ungrounded, text)
        if persona == "sisu" and name in ("safe_to_spend", "plan_goal"):
            assert ("Challenge:" in text) if locale == "en" else ("Haaste:" in text)
        if persona == "aava" and name in ("safe_to_spend", "plan_goal"):
            assert "?" in text


async def test_run_fallback_photo_without_llm(monkeypatch):
    from app.agent.fallback import run_fallback

    install_fake_analytics(monkeypatch)
    req = ChatRequest(customer_id="CUST05020", messages=[{"role": "user", "content": "Can I afford this?"}], image_base64="iVBORw0KGgo=")
    ctx = ToolContext(customer_id="CUST05020", as_of=AS_OF)
    events = [e async for e in run_fallback(req, ctx, message_id="m1")]
    text = "".join(e.data["text"] for e in events if e.event == "token")
    assert "photo" in text and events[-1].event == "done"


def test_grounding_checker():
    assert extract_numbers("**3 899,71 €** ja 20 %", "fi") == [(3899.71, False), (20.0, True)]
    assert check_grounding("You save 41 € a month, 493 € a year", [{"monthly_saving": 41.06, "total_saving": 492.75}]).ok
    bad = check_grounding("You spent 333.33 € on taxis", [{"total": 64.2}])
    assert bad.ungrounded == [333.33]
    # small counts, years and round challenge percentages are exempt
    assert check_grounding("Try a 7-day streak in 2027 and cut 25 %", [{}]).ok
