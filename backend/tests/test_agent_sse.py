"""SSE protocol: framing, orchestrator event order, fallbacks, and the FastAPI router."""

from __future__ import annotations

import json

import pytest
from tests.test_agent_fakes import FakeLLM, install_fake_analytics, text_round, tool_round

from app.agent import events as ev
from app.agent.events import ChatRequest, parse_sse
from app.agent.llm import LLMChunk, LLMUnavailable
from app.agent.orchestrator import image_content_part, run_chat

VALID_EVENTS = {"status", "tool", "widget", "token", "done", "error"}


def test_sse_framing_roundtrip():
    e = ev.token("Hei 👋 \"quoted\"\nnewline")
    wire = e.to_sse()
    assert wire.startswith("event: token\ndata: ") and wire.endswith("\n\n")
    assert wire.count("\n") == 3  # JSON stays on one data line
    [(name, data)] = parse_sse(wire)
    assert name == "token" and data["text"] == "Hei 👋 \"quoted\"\nnewline"


def test_done_event_shape():
    d = ev.done("msg_1", {"tx_count": 3, "period": "Sep 2026", "tools": ["x"]}, ["a", "b", "c"], "happy").data
    assert set(d) == {"message_id", "sources", "suggestions", "mood"}


def test_request_normalisation():
    req = ChatRequest(customer_id="CUST05020", persona="AAVA", locale="fi-FI", messages=[{"role": "user", "content": "hei"}])
    assert req.persona == "aava" and req.locale == "fi" and req.last_user_text == "hei"
    assert ChatRequest(customer_id="X", persona="nope").persona == "sisu"


def test_image_part_detects_mime():
    assert image_content_part("iVBORw0KGgo=")["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_content_part("/9j/4AAQ")["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert image_content_part("data:image/webp;base64,AAAA")["image_url"]["url"] == "data:image/webp;base64,AAAA"


async def _events(req: ChatRequest, llm) -> list[tuple[str, dict]]:
    return [(e.event, e.data) async for e in run_chat(req, llm=llm)]


def _req(text: str, **kw) -> ChatRequest:
    return ChatRequest(customer_id=kw.pop("customer_id", "CUST05020"), messages=[{"role": "user", "content": text}], **kw)


async def test_orchestrator_tool_loop_event_order(monkeypatch):
    install_fake_analytics(monkeypatch)
    monkeypatch.delenv("LLM_OFFLINE", raising=False)
    llm = FakeLLM([tool_round("query_spending", '{"subcategory": "taxi", "period": "last_month"}'), text_round("You spent ", "**64.20 €** on taxis.")])
    out = await _events(_req("How much did I spend on taxis last month?"), llm)
    names = [n for n, _ in out]
    assert set(names) <= VALID_EVENTS
    assert names[0] == "status" and names[-1] == "done"
    assert names.index("widget") < names.index("tool") < names.index("token")
    statuses = [d["label"] for n, d in out if n == "status"]
    assert "Checking your taxi spending…" in statuses
    tool = next(d for n, d in out if n == "tool")
    assert tool["name"] == "query_spending" and tool["args"]["subcategory"] == "taxi"
    assert "".join(d["text"] for n, d in out if n == "token") == "You spent **64.20 €** on taxis."
    done = out[-1][1]
    assert done["sources"]["tools"] == ["query_spending"] and done["sources"]["tx_count"] == 4
    assert done["sources"]["period"] == "Aug 2026"
    assert len(done["suggestions"]) == 3 and done["mood"] in {"happy", "neutral", "concerned", "celebrate"}
    # the tool result was fed back to the model as a tool message
    tool_msgs = [m for m in llm.calls[1]["messages"] if m["role"] == "tool"]
    assert json.loads(tool_msgs[0]["content"])["total"] == 64.2
    # thinking on while choosing tools, off when answering
    assert llm.calls[0]["thinking"] is True and llm.calls[1]["thinking"] is False


async def test_system_prompt_contains_rules_context_and_persona(monkeypatch):
    install_fake_analytics(monkeypatch)
    llm = FakeLLM([text_round("Hei!")])
    await _events(_req("Moi", persona="aava", locale="fi"), llm)
    system = llm.calls[0]["messages"][0]["content"]
    assert "Aava" in system and "Finnish" in system and "NUMBERS" in system
    assert "Balance now: 512.3" in system and "Emergency fund" in system


async def test_reasoning_is_never_streamed(monkeypatch):
    install_fake_analytics(monkeypatch)
    llm = FakeLLM([[LLMChunk(kind="reasoning"), LLMChunk(kind="content", text="Visible"), LLMChunk(kind="done", finish_reason="stop")]])
    out = await _events(_req("hi"), llm)
    assert "".join(d["text"] for n, d in out if n == "token") == "Visible"
    assert any(n == "status" and d["state"] == "thinking" for n, d in out)


async def test_concerned_mood_when_critical(monkeypatch):
    install_fake_analytics(monkeypatch)
    llm = FakeLLM([tool_round("safe_to_spend", "{}"), text_round("Careful.")])
    out = await _events(_req("safe to spend?", customer_id="CRIT"), llm)
    assert out[-1][1]["mood"] == "concerned"


async def test_falls_back_offline_when_llm_unavailable(monkeypatch):
    install_fake_analytics(monkeypatch)
    llm = FakeLLM([LLMUnavailable("down")])
    out = await _events(_req("What is safe for me to spend this week?"), llm)
    assert any(n == "widget" and d["type"] == "safe_to_spend" for n, d in out)
    text = "".join(d["text"] for n, d in out if n == "token")
    assert "23" in text  # safe_per_day from the tool
    assert out[-1][0] == "done"


async def test_empty_model_answer_is_composed_from_results(monkeypatch):
    install_fake_analytics(monkeypatch)
    llm = FakeLLM([tool_round("simulate_what_if", '{"adjustments": [{"category": "Restaurants", "change_pct": -20}]}'), [LLMChunk(kind="done", finish_reason="length")], text_round("")])
    out = await _events(_req("cut dining by 20%"), llm)
    text = "".join(d["text"] for n, d in out if n == "token")
    assert "40" in text and out[-1][0] == "done"


async def test_offline_env_forces_fallback(monkeypatch):
    install_fake_analytics(monkeypatch)
    monkeypatch.setenv("LLM_OFFLINE", "1")
    llm = FakeLLM([])
    out = await _events(_req("Help me save for a car that costs 12000"), llm)
    assert not llm.calls
    types = [d["type"] for n, d in out if n == "widget"]
    assert types == ["goal_plan", "action_buttons"]


async def test_repeated_identical_tool_call_is_cached(monkeypatch):
    calls = install_fake_analytics(monkeypatch)
    llm = FakeLLM([tool_round("plan_goal", '{"target_amount": 500}', "a"), tool_round("plan_goal", '{"target_amount": 500}', "b"), text_round("Done")])
    out = await _events(_req("save 500"), llm)
    assert sum(1 for c in calls if c[0] == "plan_goal") == 1
    assert sum(1 for n, d in out if n == "widget" and d["type"] == "goal_plan") == 1


def test_router_streams_sse(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routers.chat import router

    install_fake_analytics(monkeypatch)
    monkeypatch.setenv("LLM_OFFLINE", "1")
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        res = client.post("/api/chat", json={"customer_id": "CUST05020", "persona": "sisu", "locale": "en", "messages": [{"role": "user", "content": "What kind of spender am I?"}]})
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.text)
    names = [n for n, _ in events]
    assert names[0] == "status" and names[-1] == "done"
    assert ("widget" in names) and ("token" in names)
    assert any(d.get("type") == "spender_profile" for n, d in events if n == "widget")


def test_feedback_endpoint_falls_back_to_jsonl(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.routers.chat as chat_mod

    import app.store as store

    monkeypatch.setattr(chat_mod, "FEEDBACK_FALLBACK_PATH", tmp_path / "fb.jsonl")
    monkeypatch.delattr(store, "save_feedback")  # simulate a store without feedback support
    app = FastAPI()
    app.include_router(chat_mod.router, prefix="/api")
    with TestClient(app) as client:
        assert client.post("/api/chat/feedback", json={"message_id": "msg_1", "rating": 1}).json()["ok"] is True
        assert client.post("/api/chat/feedback", json={"message_id": "msg_1", "rating": 5}).status_code == 422
    assert json.loads((tmp_path / "fb.jsonl").read_text().strip())["rating"] == 1


def test_feedback_endpoint_uses_store():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.routers.chat as chat_mod

    app = FastAPI()
    app.include_router(chat_mod.router, prefix="/api")
    with TestClient(app) as client:
        res = client.post("/api/chat/feedback", json={"message_id": "msg_store", "rating": -1, "comment": "too long", "persona": "sisu"})
    assert res.status_code == 200 and res.json()["ok"] is True and res.json()["rating"] == -1
