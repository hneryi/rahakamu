"""Every SPEC §3.1 analytics function on the demo customers, with sanity checks."""

from __future__ import annotations

from datetime import date

import pytest

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
from app.analytics.common import add_months, month_start
from app.config import settings

AS_OF = settings.as_of_date
TX_KEYS = {"id", "date", "timestamp", "amount", "category", "basket", "merchant_id", "merchant_label",
           "mcc", "mcc_label", "icon", "balance_after", "type"}


def test_overview_shape(demo_id: str) -> None:
    o = overview.get_overview(demo_id)
    assert o["customer"]["id"] == demo_id and o["as_of"] == AS_OF.isoformat()
    assert len(o["trend_30d"]) == 31 and o["trend_30d"][-1]["balance"] == o["balance"]
    assert set(o["month"]["by_basket"]) == {"fixed", "irregular", "leak"}
    assert o["month"]["spent"] == pytest.approx(sum(o["month"]["by_basket"].values()), abs=0.05)
    assert len(o["recent_transactions"]) == 8
    assert all(set(t) == TX_KEYS for t in o["recent_transactions"])
    assert 3 <= len(o["nudges"]) <= 6
    assert len(o["goals"]) == (1 if demo_id == "CUST05014" else 2)  # seeded demo goals


def test_balance_matches_last_transaction() -> None:
    b = overview.get_balance("CUST00584")
    last = query.search_transactions("CUST00584", limit=1)["items"][0]
    assert b["balance"] == last["balance_after"]
    assert b["as_of"] == AS_OF.isoformat()


def test_basket_totals_sum_to_total_spend(demo_id: str) -> None:
    b = baskets.get_baskets(demo_id, months=6)
    assert len(b["months"]) == 6 and b["months"][-1]["partial"]
    prev = b["months"][-2]
    start = date.fromisoformat(prev["month"] + "-01")
    end = month_start(add_months(start, 1)).replace(day=1)
    q = query.query_spending(demo_id, start=start, end=end.fromordinal(end.toordinal() - 1))
    assert prev["fixed"] + prev["irregular"] + prev["leak"] == pytest.approx(q["total"], abs=0.05)
    assert set(b["explanations"]) == {"fixed", "irregular", "leak"}
    cur = b["current_month"]
    assert set(cur["top"]) == {"fixed", "irregular", "leak"}
    assert sum(cur["shares"].values()) == pytest.approx(1.0, abs=0.01) or cur["spent"] == 0


def test_query_spending_group_by_all_whitelisted() -> None:
    for g in query.GROUP_BY_SQL:
        r = query.query_spending("CUST05020", group_by=g)
        assert r["filters"]["group_by"] == g
        if g != "none":
            assert sum(x["total"] for x in r["groups"]) == pytest.approx(r["total"], abs=0.1) or g == "merchant"


def test_query_spending_rejects_unsafe_input() -> None:
    with pytest.raises(ValueError):
        query.query_spending("CUST05020", group_by="category; DROP TABLE tx")
    with pytest.raises(ValueError):
        query.query_spending("CUST05020", category="Restaurants' OR '1'='1")
    r = query.query_spending("CUST05020", merchant="x' OR '1'='1")
    assert r["count"] == 0  # bound parameter: treated as a literal merchant id


def test_taxi_last_month_question() -> None:
    r = query.query_spending("CUST05020", start="2026-08-01", end="2026-08-31",
                             category="Transportation", mcc=4121)
    assert r["period"] == {"start": "2026-08-01", "end": "2026-08-31", "days": 31}
    assert r["total"] >= 0


def test_search_transactions() -> None:
    r = query.search_transactions("CUST00586", category="Restaurants", limit=5)
    assert len(r["items"]) == 5 and r["total_count"] >= 5
    assert all(t["category"] == "Restaurants" and t["basket"] == "leak" for t in r["items"])
    assert all("#" in t["merchant_label"] or t["merchant_id"] is None for t in r["items"])
    dates = [t["timestamp"] for t in r["items"]]
    assert dates == sorted(dates, reverse=True)
    page2 = query.search_transactions("CUST00586", category="Restaurants", limit=5, offset=5)
    assert {t["id"] for t in page2["items"]}.isdisjoint({t["id"] for t in r["items"]})


def test_safe_to_spend(demo_id: str) -> None:
    s = safe_to_spend.safe_to_spend(demo_id)
    assert s["status"] in ("comfortable", "tight", "critical")
    assert s["days_until_payday"] >= 1
    assert date.fromisoformat(s["next_payday"]) > AS_OF
    assert s["safe_per_day"] >= 0 and s["safe_total"] >= 0
    assert s["safe_total"] <= max(s["balance"], 0) + 0.01
    if s["status"] == "comfortable":
        assert s["safe_per_day"] > 0
    expected = max(0.0, s["balance"] - s["upcoming_bills_total"] - s["irregular_buffer"]
                   - s["goal_contributions"])
    assert s["safe_total"] == pytest.approx(expected, abs=0.05)
    assert s["safe_this_week"] == pytest.approx(s["safe_per_day"] * min(7, s["days_until_payday"]), abs=0.05)
    assert all(date.fromisoformat(b["expected_date"]) <= date.fromisoformat(s["next_payday"])
               for b in s["upcoming_bills"])
    assert s["explanation"]


def test_recurring_finds_rent() -> None:
    r = recurring.recurring_payments("CUST00584")
    rent = [i for i in r["items"] if i["category"] == "Housing"]
    assert rent and rent[0]["cadence"] == "monthly" and 1 <= rent[0]["day_of_month"] <= 31
    assert r["monthly_total"] >= rent[0]["avg_amount"]


def test_profile_archetypes() -> None:
    expected = {"CUST05020": "latte_leaker", "CUST00584": "tightrope_walker",
                "CUST00961": "squirrel_saver"}
    for cid, key in expected.items():
        p = profile.spender_profile(cid)
        assert p["archetype"]["key"] == key
        assert all(0 <= t["score"] <= 100 and t["detail"] for t in p["traits"])
        assert len(p["archetype_scores"]) == 6


def test_benchmarks(demo_id: str) -> None:
    b = benchmarks.benchmarks(demo_id)
    assert b["peer_group"]["size"] > 50
    for c in b["categories"]:
        assert c["peer_p25"] <= c["peer_median_monthly"] <= c["peer_p75"]
        assert 0 <= c["percentile"] <= 100
    assert b["income"]["you_monthly"] > 0
    assert b["sources"]


def test_benchmarks_reads_statistics_finland_when_present() -> None:
    b = benchmarks.benchmarks("CUST05020")
    if benchmarks._fi():
        assert any(c["stat_fi_monthly"] for c in b["categories"])
    else:
        assert all(c["stat_fi_monthly"] is None for c in b["categories"])


def test_what_if() -> None:
    r = whatif.simulate_what_if("CUST05020", [{"category": "Restaurants", "change_pct": -100}], 12)
    assert r["monthly_saving"] == pytest.approx(r["baseline_monthly"], abs=0.01)
    assert r["total_saving"] == pytest.approx(r["monthly_saving"] * 12, abs=0.1)
    assert len(r["series"]) == 12
    # overlapping adjustments never double count
    both = whatif.simulate_what_if("CUST05020", [{"category": "Restaurants", "change_pct": -100},
                                                 {"basket": "leak", "change_pct": -100}])
    leak = whatif.simulate_what_if("CUST05020", [{"basket": "leak", "change_pct": -100}])
    assert both["monthly_saving"] == pytest.approx(leak["monthly_saving"], abs=0.05)
    with_ret = whatif.simulate_what_if("CUST05020", [{"basket": "leak", "change_pct": -10}], 24, 5)
    assert with_ret["with_return"] > with_ret["total_saving"]


def test_goal_crud_and_plan() -> None:
    cid = "CUST00586"
    g = goals.create_goal(cid, "Sailing boat", 8000, "2027-12-31", kind="other", saved_amount=1000)
    assert g["progress"] == pytest.approx(0.125) and g["monthly_contribution"] > 0
    g2 = goals.update_goal(cid, g["id"], add_amount=1000, name="Boat")
    assert g2["saved_amount"] == 2000 and g2["name"] == "Boat"
    assert any(x["id"] == g["id"] for x in goals.list_goals(cid))
    assert goals.delete_goal(cid, g["id"])["deleted"]
    with pytest.raises(goals.GoalNotFound):
        goals.delete_goal(cid, g["id"])

    p = goals.plan_goal(cid, 12000, "2027-09-30", "Car")
    assert p["feasibility"] in ("on_track", "stretch", "unrealistic")
    assert p["needed_per_month"] == pytest.approx(12000 / p["months"], abs=0.01)
    savings = [c["monthly_saving"] for c in p["cuts"]]
    assert savings == sorted(savings, reverse=True)
    assert all(c["basket"] == "leak" for c in p["cuts"])
    easy = goals.plan_goal("CUST00961", 1000, "2027-09-30", "Bike")
    assert easy["feasibility"] == "on_track" and easy["gap"] == 0


def test_survival_plan() -> None:
    s = survival.survival_plan("CUST00584", amount=300)
    assert s["amount"] == 300 and s["amount_mode"] == "living_money"
    assert s["risk"] in ("ok", "tight", "short") and s["tips"]
    total_budget = sum(c["budget"] for c in s["category_budgets"])
    assert total_budget <= max(s["free_money"], 0) + 0.05
    assert s["per_day"] == pytest.approx(max(s["free_money"], 0) / s["days"], abs=0.01)
    d = survival.survival_plan("CUST00001")
    assert d["amount_mode"] == "balance_minus_bills"
    assert d["free_money"] == pytest.approx(d["amount"] - d["upcoming_bills_total"], abs=0.05)
    with pytest.raises(ValueError):
        survival.survival_plan("CUST00001", until="2020-01-01")


def test_home_readiness() -> None:
    h = mortgage.home_readiness("CUST00961")
    app = h["customer_application"]
    assert app and app["decision"] == "rejected" and app["rejection_reason"] == "insufficient_collateral"
    assert h["verdict"] in ("ready", "almost", "not_yet")
    assert h["required_monthly_income"] == pytest.approx(h["loan_needed"] * 0.0184, rel=0.01)
    assert h["loan_needed"] + h["equity_needed"] == pytest.approx(h["property_price"], abs=0.05)
    other = mortgage.home_readiness("CUST05020", property_price=150000)
    assert other["customer_application"] is None and other["property_price"] == 150000


def test_nudges(demo_id: str) -> None:
    n = nudges.nudges(demo_id)
    assert 3 <= len(n) <= 6
    assert len({x["id"] for x in n}) == len(n)
    for x in n:
        assert x["kind"] in ("celebrate", "warn", "tip", "goal")
        assert x["text"] and x["action_prompt"] and x["emoji"]
