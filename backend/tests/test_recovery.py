"""Recovery state + situation-adaptive nudges and offline answers.

The rules under test are the ones the product promises:

* a negative balance is ``balance_repair`` even when cashflow is positive;
* a positive balance with negative six-month cashflow is ``cashflow_stabilizing``
  (a payday balance is a snapshot, not a permanent recovery);
* both at or above zero is ``ordinary``; missing/non-finite data is ``unknown``;
* safe-to-spend urgency stays a separate indicator, and goal contributions can make it
  tight without meaning that food or bills no longer fit;
* goal progress never moves the account balance or the recovery state.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from typing import Any

import pytest

from app.agent.fallback import compose_answer, route
from app.agent.evals.grounding import check_grounding
from app.agent.personas import get_persona
from app.agent.tools import ToolContext, execute_tool
from app.analytics import nudges, recovery
from app.analytics.common import monthly_flows

AS_OF = date(2026, 9, 18)

EXPECTED = {
    "CUST05020": ("ordinary", 7710.23, 401.85),
    "CUST00584": ("cashflow_stabilizing", 2517.67, -352.05),
    "CUST00586": ("cashflow_stabilizing", 6614.14, -1315.15),
    "CUST00961": ("ordinary", 8738.91, 3808.6),
    "CUST00001": ("ordinary", 5141.28, 308.7),
    "CUST05014": ("balance_repair", -784.58, -1527.02),
}

RECOVERY_ACTIONS = {
    "en": [
        "How do I get back to a positive balance?",
        "How do I stop my buffer from shrinking?",
        "Where does the six-month spending gap come from?",
        "How do I make it to payday — which bills come first?",
        "What is an emergency buffer and how do I start one?",
    ],
    "fi": [
        "Miten pääsen takaisin plussalle?",
        "Miten estän puskurin hupenemisen?",
        "Mistä kuuden kuukauden menoero muodostuu?",
        "Miten selviän palkkapäivään asti ja mitkä laskut tulevat ensin?",
        "Mikä on puskurirahasto ja miten aloitan sen?",
    ],
    "sv": [
        "Hur kommer jag tillbaka till plus?",
        "Hur hindrar jag att bufferten krymp?",
        "Var kommer utgiftsgapet på sex månader från?",
        "Hur klarar jag mig till lönedagen och vilka räkningar kommer först?",
        "Vad är en buffert och hur börjar jag en?",
    ],
}


# ------------------------------------------------------------------ pure classification
@pytest.mark.parametrize(
    "balance,surplus,state",
    [
        (-784.58, -1527.02, "balance_repair"),  # deficit + negative balance
        (-784.58, 401.85, "balance_repair"),  # negative balance, positive cashflow
        (-0.01, 0.0, "balance_repair"),  # one cent below zero
        (0.0, -0.01, "cashflow_stabilizing"),  # zero balance, one cent deficit
        (0.0, 0.0, "ordinary"),
        (2517.67, -352.05, "cashflow_stabilizing"),  # payday balance, shrinking buffer
        (6614.14, 1315.15, "ordinary"),
        (None, 5.0, "unknown"),
        (5.0, None, "unknown"),
        (float("nan"), 5.0, "unknown"),
        (5.0, float("inf"), "unknown"),
        (float("-inf"), 0.0, "unknown"),
        ("n/a", 5.0, "unknown"),
    ],
)
def test_classify_boundaries(balance: Any, surplus: Any, state: str) -> None:
    assert recovery.classify(balance, surplus) == state


def test_classify_rounds_to_cents() -> None:
    assert recovery.classify(0.004, 0.0) == "ordinary"
    assert recovery.classify(-0.004, 0.0) == "ordinary"
    assert recovery.classify(0.0, -0.006) == "cashflow_stabilizing"


def test_classification_of_every_demo_customer() -> None:
    for cid, (state, balance, surplus) in EXPECTED.items():
        rec = recovery.recovery(cid)
        assert rec["state"] == state, cid
        assert rec["balance"] == pytest.approx(balance, abs=0.01)
        assert rec["monthly_surplus"] == pytest.approx(surplus, abs=0.01)
        assert rec["months"] == 6
        flows = monthly_flows(cid, 6)
        assert rec["monthly_income"] == flows["income"]
        assert rec["monthly_spending"] == flows["spending"]
        assert rec["tx_count"] > 0


def test_recovery_states_agree_with_flows_and_balance() -> None:
    for cid in EXPECTED:
        rec = recovery.recovery(cid)
        expected = recovery.classify(rec["balance"], rec["monthly_surplus"])
        assert rec["state"] == expected


# ------------------------------------------------------- synthetic edge cases (no ledger)
def _fake_inputs(monkeypatch, balance: float, surplus: float, tx_count: int = 40,
                 goals: list[dict[str, Any]] | None = None, sts: dict[str, Any] | None = None) -> None:
    monkeypatch.setattr(recovery, "current_balance", lambda customer_id: balance)
    monkeypatch.setattr(recovery, "monthly_flows", lambda customer_id, months=6: {
        "income": 1000.0, "spending": 1000.0 - surplus, "saving": 0.0, "surplus": surplus,
        "fixed": 500.0, "irregular": 300.0, "leak": 200.0 - surplus})
    monkeypatch.setattr(recovery, "tx_count_and_period", lambda customer_id, start=None, end=None: {
        "tx_count": tx_count, "period": "2026-03-01..2026-08-31"})
    import app.analytics.goals as goals_mod

    rows = goals if goals is not None else []
    monkeypatch.setattr(goals_mod, "list_goals", lambda customer_id: rows)
    monkeypatch.setattr(recovery, "safe_to_spend", lambda customer_id: sts or {
        "status": "comfortable", "safe_per_day": 20.0, "days_until_payday": 5,
        "goal_contributions": 0.0, "upcoming_bills": [], "upcoming_bills_total": 0.0})


def test_payday_positive_balance_with_negative_surplus_stays_stabilizing(monkeypatch) -> None:
    _fake_inputs(monkeypatch, balance=1800.0, surplus=-400.0)
    rec = recovery.recovery("CUST05014")
    assert rec["state"] == "cashflow_stabilizing"  # a payday balance is not a recovery
    assert rec["deficit"] == 400.0
    assert rec["planned_monthly_change"] == pytest.approx(400.0 + rec["goal_monthly_need"], abs=0.01)


def test_missing_or_non_finite_data_is_unknown(monkeypatch) -> None:
    _fake_inputs(monkeypatch, balance=0.0, surplus=0.0, tx_count=0)
    assert recovery.recovery("CUST05014")["state"] == "unknown"
    _fake_inputs(monkeypatch, balance=float("nan"), surplus=0.0)
    rec = recovery.recovery("CUST05014")
    assert rec["state"] == "unknown"
    assert rec["balance"] is None and rec["safe_per_day"] is None
    json.dumps(rec, allow_nan=False)


def test_planned_change_is_deficit_plus_goal_need(monkeypatch) -> None:
    goal = {"id": "g1", "name": "Back in the black", "emoji": "🎯", "target_amount": 784.58,
            "saved_amount": 0.0, "deadline": "2027-09-18", "monthly_contribution": 65.38, "progress": 0.0}
    _fake_inputs(monkeypatch, balance=-784.58, surplus=-1527.02, goals=[goal])
    rec = recovery.recovery("CUST05014")
    assert rec["goal_monthly_need"] == 65.38
    assert rec["planned_monthly_change"] == pytest.approx(1592.40, abs=0.01)


def test_goal_saved_amount_does_not_move_balance_or_state(monkeypatch) -> None:
    goal = {"id": "g1", "name": "Back in the black", "emoji": "🎯", "target_amount": 784.58,
            "saved_amount": 0.0, "deadline": "2027-09-18", "monthly_contribution": 65.38, "progress": 0.0}
    _fake_inputs(monkeypatch, balance=-784.58, surplus=-1527.02, goals=[goal])
    before = recovery.recovery("CUST05014")
    _fake_inputs(monkeypatch, balance=-784.58, surplus=-1527.02,
                 goals=[{**goal, "saved_amount": 200.0, "progress": 0.25}])
    after = recovery.recovery("CUST05014")
    for key in ("state", "balance", "monthly_surplus", "deficit", "planned_monthly_change"):
        assert before[key] == after[key], key


def test_goal_reserved_tightness_is_flagged_not_insolvency(monkeypatch) -> None:
    _fake_inputs(monkeypatch, balance=500.0, surplus=100.0, sts={
        "status": "tight", "safe_per_day": 3.0, "days_until_payday": 6,
        "goal_contributions": 80.0, "upcoming_bills": [], "upcoming_bills_total": 0.0})
    rec = recovery.recovery("CUST05014")
    assert rec["state"] == "ordinary" and rec["urgency"] == "tight"
    assert rec["goal_reservations_present"] is True
    assert rec["deficit"] == 0.0


# --------------------------------------------------------------------------- nudges
def test_balance_repair_nudges_for_joni() -> None:
    n = nudges.nudges("CUST05014")
    assert 3 <= len(n) <= 6
    ids = [x["id"] for x in n]
    assert ids[:3] == ["recovery_balance", "recovery_bills", "recovery_deficit"]
    assert "784.58" in n[0]["text"] or "784,58" in n[0]["text"]
    assert "1527" in "".join(ch for ch in n[2]["text"] if ch.isdigit())
    assert n[0]["action_prompt"]
    assert not {"archetype", "savings_rate", "safe_to_spend_low", "leak_pace_low"} & set(ids)
    assert all("benchmark" not in i and "compare" not in i for i in ids)


def test_cashflow_stabilizing_nudges_warn_about_the_buffer() -> None:
    for cid in ("CUST00584", "CUST00586"):
        n = nudges.nudges(cid)
        assert n[0]["id"] == "recovery_cashflow"
        assert "puskur" in n[0]["text"] or "buffer" in n[0]["text"]
        assert any(x["id"] == "recovery_deficit" for x in n)
        assert 3 <= len(n) <= 6


def test_ordinary_customers_keep_the_generic_nudges() -> None:
    for cid in ("CUST05020", "CUST00961", "CUST00001"):
        ids = {x["id"] for x in nudges.nudges(cid)}
        assert not any(i.startswith("recovery_") for i in ids)


def test_unknown_nudges_are_neutral_and_not_green() -> None:
    n = nudges._unknown_nudges()
    assert n and all(x["emoji"] != "🟢" for x in n)
    assert "guess" in n[0]["text"] or "arvaa" in n[0]["text"]


def test_recovery_nudges_are_localised_in_all_languages(monkeypatch) -> None:
    from app.i18n import use_locale

    for loc, marker in (("en", "below zero"), ("fi", "miinuksella"), ("sv", "under noll")):
        with use_locale(loc):
            n = nudges.nudges("CUST05014")
        assert marker in n[0]["text"], (loc, n[0]["text"])
        assert all(x["action_prompt"] for x in n)


# ------------------------------------------------------- offline answers for the actions
def test_recovery_action_prompts_route_to_existing_tools() -> None:
    expected = {
        "en": ["get_overview", "get_overview", "query_spending", "survival_plan", "explain_concept"],
        "fi": ["get_overview", "get_overview", "query_spending", "survival_plan", "explain_concept"],
        "sv": ["get_overview", "get_overview", "query_spending", "survival_plan", "explain_concept"],
    }
    for loc, texts in RECOVERY_ACTIONS.items():
        for text, tool in zip(texts, expected[loc]):
            intent = route(text, loc, AS_OF)
            assert intent.calls[0][0] == tool, (loc, text, intent.name)


def _answer(cid: str, text: str, loc: str, persona: str) -> tuple[str, Any]:
    async def run() -> tuple[str, Any]:
        intent = route(text, loc, AS_OF)
        ctx = ToolContext(customer_id=cid, locale=loc, persona=persona, as_of=AS_OF, user_text=text)
        results = [(name, await execute_tool(name, args, ctx)) for name, args in intent.calls]
        return compose_answer(results, get_persona(persona), loc, user_text=text, recovery_context=recovery.recovery(cid)), results[0][1]

    return asyncio.run(run())


@pytest.mark.parametrize("persona", ["sisu", "aava"])
@pytest.mark.parametrize("locale", ["en", "fi", "sv"])
def test_recovery_answers_are_grounded_and_avoid_generic_closers(persona: str, locale: str) -> None:
    text, res = _answer("CUST05014", RECOVERY_ACTIONS[locale][0], locale, persona)
    assert text.strip()
    report = check_grounding(text, [res.llm_payload, res.raw], question=RECOVERY_ACTIONS[locale][0], locale=locale)
    assert report.ok, (report.ungrounded, text)
    low = text.lower()
    assert "lisää jotain yhteen tavoitteeseen" not in low  # generic "add to a goal this week" closer
    assert "add something to one goal" not in low and "pay yourself first" not in low
    assert "maksa ensin itsellesi" not in low
    if persona == "aava":
        assert "?" in text


@pytest.mark.parametrize("locale", ["en", "fi", "sv"])
def test_recovery_answer_uses_the_shared_numbers(locale: str) -> None:
    text, _ = _answer("CUST05014", RECOVERY_ACTIONS[locale][0], locale, "sisu")
    compact = "".join(ch for ch in text if ch.isdigit())
    assert "784" in compact and "1527" in compact and "1592" in compact
    # cashflow is negative here, so the answer may say so, and essentials come first
    assert ("alijääm" in text.lower() or "underskott" in text.lower() or "deficit" in text.lower())
    assert ("välttämättöm" in text.lower() or "essential" in text.lower() or "nödvändig" in text.lower())


@pytest.mark.parametrize("balance,surplus,state", [(-100, 120, "balance_repair"), (1800, -400, "cashflow_stabilizing"), (-100, 0, "balance_repair")])
def test_payday_snapshot_answer_does_not_overstate_the_trend(balance, surplus, state) -> None:
    from app.agent import fallback

    raw = {
        "balance": balance, "month": {"income": 2000.0, "spent": 1500.0},
        "safe_to_spend": {"safe_per_day": 20.0, "status": "comfortable"},
        "recovery": {"state": state, "months": 6, "balance": balance, "monthly_surplus": surplus,
                     "deficit": max(0, -surplus), "goal_monthly_need": 0.0},
    }
    text, tone = fallback._t_get_overview(raw, {}, "en")
    assert tone == "concern"
    assert "no ongoing deficit" not in text and "not a trend" not in text
    assert ("averaged a surplus" in text) == (surplus >= 0)


def test_deficit_answer_mentions_the_six_month_groups() -> None:
    text, _ = _answer("CUST05014", RECOVERY_ACTIONS["fi"][2], "fi", "sisu")
    assert "kuukau" in text.lower() or "6" in text
    assert "€" in text
