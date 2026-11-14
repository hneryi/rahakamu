"""REST smoke tests via FastAPI's TestClient (every SPEC §3.2 route except /chat)."""

from __future__ import annotations

import time

import pytest

from app.config import settings

GET_ROUTES = [
    "overview", "transactions?limit=5", "spending?group_by=category", "baskets?months=3",
    "safe-to-spend", "recurring", "profile", "benchmarks", "goals", "survival?amount=300",
    "home-readiness", "nudges",
]


def test_health_never_leaks_key(client) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and isinstance(body["llm"]["primary"], bool)
    if settings.verda_inference_key:
        assert settings.verda_inference_key.get_secret_value() not in r.text


def test_demo_customers(client) -> None:
    r = client.get("/api/customers/demo")
    assert r.status_code == 200
    ids = [c["customer_id"] for c in r.json()]
    assert ids[:2] == ["CUST05020", "CUST00584"] and len(ids) == 6
    assert all({"name", "age", "postal_code", "tagline", "avatar_emoji"} <= set(c) for c in r.json())
    joni = r.json()[5]
    assert joni["customer_id"] == "CUST05014" and joni["name"] == "Joni"
    assert joni["age"] == 23 and joni["postal_code"] == "00487"
    assert joni["tagline"].startswith("An unexpected repair")


def test_joni_is_the_negative_balance_demo(client) -> None:
    bal = client.get("/api/customers/CUST05014/balance").json()
    assert bal["balance"] == pytest.approx(-784.58)
    goals = client.get("/api/customers/CUST05014/goals").json()
    assert len(goals) == 1
    g = goals[0]
    assert (g["name"], g["kind"], g["target_amount"], g["saved_amount"]) == ("Back in the black", "other", 784.58, 0)
    assert g["deadline"] == "2027-09-18"
    fi = client.get("/api/customers/CUST05014/goals", params={"locale": "fi"}).json()
    assert fi[0]["name"] == "Takaisin plussalle"
    sv = client.get("/api/customers/CUST05014/goals", params={"locale": "sv"}).json()
    assert sv[0]["name"] == "Tillbaka på plus"
    demo = client.get("/api/customers/demo", params={"locale": "fi"}).json()
    assert demo[5]["tagline"].startswith("Yllättävä remontti")
    demo_sv = client.get("/api/customers/demo", params={"locale": "sv"}).json()
    assert demo_sv[5]["tagline"].startswith("En oväntad reparation")


@pytest.mark.parametrize("cid", ["CUST05020", "CUST00584"])
@pytest.mark.parametrize("route", GET_ROUTES)
def test_get_routes(client, cid: str, route: str) -> None:
    r = client.get(f"/api/customers/{cid}/{route}")
    assert r.status_code == 200, r.text


def test_unknown_customer_404(client) -> None:
    for route in GET_ROUTES:
        assert client.get(f"/api/customers/CUST99999/{route}").status_code == 404


def test_validation_errors(client) -> None:
    assert client.get("/api/customers/CUST05020/spending?group_by=drop").status_code == 422
    assert client.get("/api/customers/CUST05020/spending?category=Nope").status_code == 422
    assert client.get("/api/customers/CUST05020/transactions?start=yesterday").status_code == 422
    bad = client.post("/api/customers/CUST05020/what-if", json={"adjustments": [{"change_pct": -10}]})
    assert bad.status_code == 422


def test_what_if_post(client) -> None:
    r = client.post("/api/customers/CUST05020/what-if",
                    json={"adjustments": [{"category": "Restaurants", "change_pct": -20}],
                          "horizon_months": 12, "invest_return_pct": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["monthly_saving"] == pytest.approx(body["baseline_monthly"] * 0.2, abs=0.02)


def test_goal_lifecycle(client) -> None:
    base = "/api/customers/CUST00584/goals"
    r = client.post(base, json={"name": "Bike", "target_amount": 600, "deadline": "2027-05-31",
                                "kind": "other", "emoji": "🚲"})
    assert r.status_code == 201
    gid = r.json()["id"]
    r = client.patch(f"{base}/{gid}", json={"add_amount": 100})
    assert r.status_code == 200 and r.json()["saved_amount"] == 100
    assert client.delete(f"{base}/{gid}").status_code == 200
    assert client.delete(f"{base}/{gid}").status_code == 404
    assert client.patch(f"{base}/nope", json={"name": "x"}).status_code == 404
    plan = client.post(f"{base}/plan", json={"target_amount": 12000, "name": "Car"})
    assert plan.status_code == 200 and plan.json()["feasibility"] in ("on_track", "stretch", "unrealistic")


def test_content_routes(client) -> None:
    r = client.get("/api/lessons?locale=fi&customer_id=CUST05020")
    assert r.status_code == 200
    lessons = r.json()["lessons"]
    if lessons:
        assert isinstance(lessons[0]["title"], str)
        assert all("unlocked" in les for les in lessons)
    assert client.get("/api/personas").status_code == 200
    assert client.get("/api/baskets/rules").status_code == 200


def test_overview_is_fast_when_warm(client) -> None:
    client.get("/api/customers/CUST00001/overview")
    t = time.perf_counter()
    assert client.get("/api/customers/CUST00001/overview").status_code == 200
    # target is < 300 ms; generous bound so a loaded CI machine doesn't flake
    assert time.perf_counter() - t < 1.5
