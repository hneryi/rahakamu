#!/usr/bin/env python3
"""Minimal SPEC-compliant stub of the SPankkiBot API (docs/SPEC.md §3.2 + §4.2), for e2e self-tests.

Used to (a) self-test e2e/api_smoke.py and (b) let the Playwright UI tests run when the real
backend is not up. Canned data only — no DuckDB, no LLM. NOT the product backend.

    uv run --with fastapi --with uvicorn python e2e/mock_backend.py [--port 8000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

AS_OF = "2026-09-18"
DEMO = [
    ("CUST05020", "Emma", 21, "00100", "Student, small income, leaky", "🎓"),
    ("CUST00584", "Leo", 22, "33100", "Dips below zero", "🛹"),
    ("CUST00586", "Mika", 39, "02100", "High income, big leaks", "💼"),
    ("CUST00961", "Sanna", 41, "40100", "Dreaming of a home", "🏡"),
    ("CUST00001", "Pirjo", 63, "20100", "Steady saver", "🌿"),
]
DEMO_BY_ID = {d[0]: d for d in DEMO}
GOALS: dict[str, list[dict]] = {}

app = FastAPI(title="SPankkiBot mock")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def cust(cid: str):
    if cid not in DEMO_BY_ID and not cid.startswith("CUST0"):
        raise HTTPException(404, "unknown customer")
    return DEMO_BY_ID.get(cid, (cid, "Customer", 35, "00100", "", "🙂"))


def tx(i: int, cat="Restaurants", basket="leak", amt=-12.5):
    return {"id": f"tx{i}", "date": "2026-09-17", "timestamp": "2026-09-17T12:30:00", "amount": amt, "category": cat,
            "basket": basket, "merchant_id": "MRC-RES-0012", "merchant_label": "Café #12", "mcc": 5812,
            "mcc_label": "Restaurant", "icon": "🍽️", "balance_after": 640.25 - i, "type": "purchase"}


def goals_for(cid: str) -> list[dict]:
    if cid not in GOALS:
        GOALS[cid] = [
            {"id": "g1", "name": "Emergency fund", "emoji": "🛟", "kind": "emergency", "target_amount": 1000.0, "saved_amount": 320.0,
             "deadline": "2027-03-31", "monthly_contribution": 60.0, "progress": 0.32, "created_at": "2026-06-01T10:00:00"},
            {"id": "g2", "name": "Laptop", "emoji": "💻", "kind": "gadget", "target_amount": 1200.0, "saved_amount": 450.0,
             "deadline": "2027-01-31", "monthly_contribution": 80.0, "progress": 0.375, "created_at": "2026-07-01T10:00:00"},
        ]
    return GOALS[cid]


SAFE = {"balance": 640.25, "next_payday": "2026-09-25", "days_until_payday": 7,
        "upcoming_bills": [{"label": "Rent", "amount": 420.0, "expected_date": "2026-10-01"}],
        "irregular_buffer": 40.0, "goal_contributions": 20.0, "safe_total": 160.25, "safe_per_day": 22.89,
        "safe_this_week": 160.25, "status": "tight", "explanation": "Balance minus bills and buffers until payday."}
NUDGES = [{"id": f"n{i}", "kind": k, "text": t, "emoji": e, "action_prompt": p} for i, (k, t, e, p) in enumerate([
    ("warn", "Restaurants are 30% above your usual.", "🍔", "How much did I spend on restaurants last month?"),
    ("celebrate", "3 weeks without overdraft!", "🎉", "How am I doing?"),
    ("tip", "Your leak basket is 24% of spending.", "💧", "What is my leak basket?"),
])]
SPEND = {"filters": {}, "total": 182.4, "count": 14, "avg_tx": 13.03, "period": {"start": "2026-08-01", "end": "2026-08-31"},
         "groups": [{"key": "Restaurants", "label": "Restaurants", "total": 182.4, "count": 14}]}
PROFILE = {"archetype": {"key": "latte_leaker", "name": "Latte Leaker", "emoji": "☕", "description": "Many small treats."},
           "traits": [{"key": "small_tx", "label": "Small purchases", "score": 78, "detail": "11 per week"}],
           "savings_rate": 0.04, "leak_share": 0.31, "weekend_share": 0.38, "small_tx_per_week": 11.2, "late_night_share": 0.05, "volatility": 0.4}
WHATIF = {"baseline_monthly": 180.0, "new_monthly": 144.0, "monthly_saving": 36.0, "horizon_months": 12, "total_saving": 432.0,
          "with_return": 432.0, "per_item": [{"label": "Restaurants", "monthly_saving": 36.0}],
          "series": [{"month": m, "cumulative": 36.0 * m} for m in range(1, 13)]}
PLAN = {"name": "Car", "target_amount": 12000.0, "saved_amount": 0.0, "deadline": "2027-06-30", "months": 9, "needed_per_month": 1333.33,
        "current_monthly_surplus": 150.0, "gap": 1183.33, "feasibility": "unrealistic", "suggested_deadline": "2029-12-31",
        "cuts": [{"label": "Restaurants", "category": "Restaurants", "basket": "leak", "current_monthly": 180.0, "cut_pct": 30,
                  "monthly_saving": 54.0, "why": "Cook at home twice a week."}], "cuts_total": 54.0, "summary": "Stretch the deadline."}


@app.get("/api/health")
def health():
    return {"status": "ok", "as_of": AS_OF, "llm": {"primary": False}}


@app.get("/api/customers/demo")
def demo():
    return [{"customer_id": c, "name": n, "age": a, "postal_code": p, "tagline": t, "avatar_emoji": e} for c, n, a, p, t, e in DEMO]


@app.get("/api/customers/{cid}/overview")
def overview(cid: str):
    c = cust(cid)
    return {"customer": {"id": c[0], "name": c[1], "age": c[2], "postal_code": c[3]}, "as_of": AS_OF, "balance": 640.25,
            "trend_30d": [{"date": f"2026-09-{d:02d}", "balance": 600.0 + d} for d in range(1, 19)],
            "month": {"income": 900.0, "spent": 560.0, "saved": 50.0, "by_basket": {"fixed": 320.0, "irregular": 60.0, "leak": 180.0}},
            "safe_to_spend": SAFE, "goals": goals_for(cid), "recent_transactions": [tx(i) for i in range(8)], "nudges": NUDGES}


@app.get("/api/customers/{cid}/transactions")
def transactions(cid: str, category: str | None = None, basket: str | None = None, limit: int = 50, offset: int = 0,
                 start: str | None = None, end: str | None = None, merchant: str | None = None, text: str | None = None):
    cust(cid)
    items = [tx(i, category or "Restaurants", basket or "leak") for i in range(min(limit, 10))]
    return {"items": items, "total_count": 42}


@app.get("/api/customers/{cid}/spending")
def spending(cid: str, group_by: str = "none", category: str | None = None, basket: str | None = None,
             start: str | None = None, end: str | None = None):
    cust(cid)
    if group_by == "basket":
        return {**SPEND, "total": 560.0, "groups": [{"key": k, "label": k, "total": v, "count": 5} for k, v in
                                                     (("fixed", 320.0), ("irregular", 60.0), ("leak", 180.0))]}
    return SPEND


@app.get("/api/customers/{cid}/baskets")
def baskets(cid: str, months: int = 6):
    cust(cid)
    m = {"fixed": 320.0, "irregular": 60.0, "leak": 180.0, "income": 900.0, "saving": 50.0}
    return {"months": [{"month": f"2026-{mm:02d}", **m} for mm in range(10 - months, 10)],
            "current_month": {"month": "2026-09", **m, "top": {"fixed": [{"label": "Rent", "total": 250.0}],
                                                                 "irregular": [{"label": "Pharmacy", "total": 30.0}],
                                                                 "leak": [{"label": "Restaurants", "total": 120.0}]}},
            "explanations": {"fixed": "Must-pay, every month.", "irregular": "Must-pay, now and then.", "leak": "Small stuff that adds up."}}


@app.get("/api/customers/{cid}/safe-to-spend")
def safe(cid: str):
    cust(cid)
    return SAFE


@app.get("/api/customers/{cid}/recurring")
def recurring(cid: str):
    cust(cid)
    return {"items": [{"label": "Streaming #3", "category": "Entertainment", "merchant_id": "MRC-ENT-0003", "avg_amount": 12.99,
                       "cadence": "monthly", "day_of_month": 5, "last_date": "2026-09-05", "basket": "fixed"}], "monthly_total": 12.99}


@app.get("/api/customers/{cid}/profile")
def profile(cid: str):
    cust(cid)
    return PROFILE


@app.get("/api/customers/{cid}/benchmarks")
def benchmarks(cid: str):
    cust(cid)
    row = {"you_monthly": 180.0, "peer_median_monthly": 120.0, "peer_p25": 80.0, "peer_p75": 170.0, "percentile": 78, "stat_fi_monthly": None}
    return {"peer_group": {"label": "Age 18-25 in dataset", "size": 812}, "categories": [{"category": "Restaurants", **row}],
            "income": row, "savings_rate": {"you": 0.04, "peer_median": 0.08},
            "sources": [{"name": "Statistics Finland", "url": "https://stat.fi", "note": "Household budget survey"}]}


@app.post("/api/customers/{cid}/what-if")
async def what_if(cid: str, req: Request):
    cust(cid)
    b = await req.json()
    h = int(b.get("horizon_months", 12))
    return {**WHATIF, "horizon_months": h, "series": [{"month": m, "cumulative": 36.0 * m} for m in range(1, h + 1)]}


@app.get("/api/customers/{cid}/goals")
def list_goals(cid: str):
    cust(cid)
    return goals_for(cid)


@app.post("/api/customers/{cid}/goals", status_code=201)
async def create_goal(cid: str, req: Request):
    b = await req.json()
    g = {"id": uuid.uuid4().hex[:8], "name": b["name"], "emoji": b.get("emoji"), "kind": b.get("kind", "other"),
         "target_amount": float(b["target_amount"]), "saved_amount": float(b.get("saved_amount", 0)), "deadline": b.get("deadline"),
         "monthly_contribution": None, "progress": float(b.get("saved_amount", 0)) / float(b["target_amount"]), "created_at": AS_OF + "T12:00:00"}
    goals_for(cid).append(g)
    return g


@app.post("/api/customers/{cid}/goals/plan")
async def plan(cid: str, req: Request):
    b = await req.json()
    return {**PLAN, "target_amount": float(b["target_amount"]), "name": b.get("name")}


@app.patch("/api/customers/{cid}/goals/{gid}")
async def patch_goal(cid: str, gid: str, req: Request):
    b = await req.json()
    for g in goals_for(cid):
        if g["id"] == gid:
            g.update(b)
            g["progress"] = min(1.0, g["saved_amount"] / g["target_amount"])
            return g
    raise HTTPException(404)


@app.delete("/api/customers/{cid}/goals/{gid}")
def delete_goal(cid: str, gid: str):
    GOALS[cid] = [g for g in goals_for(cid) if g["id"] != gid]
    return {"deleted": gid}


@app.get("/api/customers/{cid}/survival")
def survival(cid: str, amount: float | None = None, until: str | None = None):
    cust(cid)
    a = amount if amount is not None else 640.25
    return {"amount": a, "until": until or "2026-09-25", "days": 7, "upcoming_bills_total": 0.0, "bills": [], "free_money": a,
            "per_day": round(a / 7, 2), "per_week": a, "category_budgets": [{"category": "Groceries", "budget": 60.0, "typical": 75.0}],
            "risk": "tight", "shortfall": 0.0, "tips": ["Cook in batches."]}


@app.get("/api/customers/{cid}/home-readiness")
def home(cid: str, property_price: float | None = None):
    cust(cid)
    p = property_price or 200000.0
    return {"property_price": p, "loan_needed": p * 0.9, "equity_needed": p * 0.1, "your_equity_estimate": 4000.0,
            "required_monthly_income": 4200.0, "your_monthly_income": 2900.0, "ltv": 0.9, "verdict": "not_yet",
            "gaps": ["Equity short by 21 000 €"], "dataset_note": "Based on 200 mortgage applications.", "customer_application": None}


@app.get("/api/customers/{cid}/nudges")
def nudges(cid: str):
    cust(cid)
    return NUDGES


@app.get("/api/lessons")
def lessons(locale: str = "en"):
    t = "Kolme koria" if locale == "fi" else "The three baskets"
    return [{"id": "baskets", "title": t, "emoji": "🧺", "body": "…"}]


@app.get("/api/personas")
def personas():
    return {"sisu": {"name": "Sisu", "emoji": "🐻", "color": "#F5A524"}, "aava": {"name": "Aava", "emoji": "🦉", "color": "#3DD9B4"}}


@app.post("/api/chat")
async def chat(req: Request):
    b = await req.json()
    fi = b.get("locale") == "fi"

    async def gen():
        def ev(t, d):
            return f"event: {t}\ndata: {json.dumps(d, ensure_ascii=False)}\n\n"

        yield ev("status", {"state": "thinking", "label": "Ajattelen…" if fi else "Thinking…"})
        await asyncio.sleep(0.05)
        yield ev("status", {"state": "tool", "label": "Checking your restaurant spending…"})
        yield ev("tool", {"name": "query_spending", "args": {"category": "Restaurants"}, "summary": "182.40 € over 14 tx"})
        yield ev("widget", {"id": "w1", "type": "bar_chart", "data": {"title": "Restaurants", "unit": "€",
                                                                       "bars": [{"label": "Jul", "value": 150.0}, {"label": "Aug", "value": 182.4, "highlight": True}]}})
        yield ev("status", {"state": "writing", "label": "Writing…"})
        text = ("Käytit ravintoloihin **182,40 €** elokuussa ja se on vuotokorissa." if fi
                else "You spent **182.40 €** on restaurants last month — that's your leak basket.")
        for w in text.split(" "):
            yield ev("token", {"text": w + " "})
            await asyncio.sleep(0.01)
        yield ev("done", {"message_id": uuid.uuid4().hex, "sources": {"tx_count": 14, "period": "Aug 2026", "tools": ["query_spending"]},
                          "suggestions": ["What if I cut 20%?", "Show transactions", "What kind of spender am I?"], "mood": "concerned"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/api/chat/feedback")
async def feedback(req: Request):
    await req.json()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    uvicorn.run(app, host="127.0.0.1", port=ap.parse_args().port, log_level="warning")
