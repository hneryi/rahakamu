"""Public-demo hardening: rate limits, size limits, LLM slots, health, CORS, error bodies.

Each test names the behaviour it protects. Limits are per worker and configured through
``app.config.settings``, so tests lower them with ``monkeypatch`` and reset the in-memory
counters around every test.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import limits, store
from app.agent import events as ev
from app.agent.events import parse_sse
from app.config import settings
from app.i18n import use_locale

LOCALES = ("en", "fi", "sv")
TEXT = {
    "en": "How much money can I spend this week?",
    "fi": "Paljonko minulla on rahaa käytettävissä tällä viikolla?",
    "sv": "Hur mycket pengar kan jag använda den här veckan?",
}
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()
DONE = ev.done("msg_t", {"tx_count": 0, "period": "", "tools": []}, [], "neutral")


@pytest.fixture(autouse=True)
def _fresh_limits():
    limits.reset_limiters()
    yield
    limits.reset_limiters()


def _msg(code: str, locale: str) -> str:
    with use_locale(locale):
        return limits.message(code)


def _fake_run(record: list | None = None, events: list | None = None, boom: bool = False):
    """Stand-in for ``run_chat``: replays ``events`` (default: one token and ``done``)."""

    async def run(req, *, force_offline: bool = False, **_):
        if record is not None:
            record.append(force_offline)
        for event in [ev.token("hi"), DONE] if events is None else events:
            yield event
        if boom:
            raise RuntimeError("secret internal detail")

    return run


def _chat(client, text: str = TEXT["en"], cid: str = "CUST05020", locale: str = "en", headers=None, **extra):
    body = {"customer_id": cid, "locale": locale, "messages": [{"role": "user", "content": text}], **extra}
    return client.post("/api/chat", json=body, headers=headers)


@pytest.fixture
def fast_chat(monkeypatch):
    """Chat route with the orchestrator replaced, so limit tests do no analytics work."""
    import app.routers.chat as chat_mod

    record: list[bool] = []
    monkeypatch.setattr(chat_mod, "run_chat", _fake_run(record))
    return record


# ------------------------------------------------------------------------ limiter unit
def test_sliding_window_allows_up_to_limit_then_reports_wait():
    lim = limits.SlidingWindowLimiter(window_s=60)
    assert lim.hit("a", 2) == 0.0 and lim.hit("a", 2) == 0.0
    wait = lim.hit("a", 2)
    assert 0 < wait <= 60
    assert lim.hit("b", 2) == 0.0  # other keys are unaffected
    assert lim.hit("a", 0) == 0.0  # 0 switches the limit off


def test_sliding_window_recovers_and_does_not_count_rejections():
    lim = limits.SlidingWindowLimiter(window_s=0.05)
    assert lim.hit("a", 1) == 0.0
    for _ in range(20):  # hammering while blocked must not extend the block
        assert lim.hit("a", 1) > 0
    time.sleep(0.07)
    assert lim.hit("a", 1) == 0.0


def test_sliding_window_bounds_memory_under_many_keys():
    lim = limits.SlidingWindowLimiter(window_s=60, max_keys=50)
    for i in range(500):
        lim.hit(f"k{i}", 5)
    assert len(lim._hits) <= 50


def _request(peer: str, forwarded: str | None = None):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_client_ip_trusts_forwarded_header_only_from_local_proxy():
    # Caddy on the same host appends the real peer as the last entry
    assert limits.client_ip(_request("127.0.0.1", "6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    assert limits.client_ip(_request("127.0.0.1")) == "127.0.0.1"
    # a direct caller cannot pick its own identity
    assert limits.client_ip(_request("198.51.100.7", "1.2.3.4")) == "198.51.100.7"


@pytest.mark.parametrize("code", ["rate_limited", "message_too_long", "history_too_long", "image_too_large",
                                  "image_invalid", "body_too_large", "server_error", "out_of_range"])
def test_limit_messages_exist_in_three_languages(code):
    texts = {_msg(code, loc) for loc in LOCALES}
    assert len(texts) == 3 and all(len(t) > 10 for t in texts)


def test_check_image_accepts_real_images_and_rejects_the_rest(monkeypatch):
    assert limits.check_image(PNG) is None
    assert limits.check_image("data:image/png;base64," + PNG) is None
    assert limits.check_image(base64.b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 32).decode()) is None
    assert limits.check_image(base64.b64encode(b"RIFF\x00\x00\x00\x00WEBPVP8 ").decode()) is None
    assert limits.check_image(base64.b64encode(b"just some text, not an image").decode()) == "image_invalid"
    assert limits.check_image("!!! not base64 !!!") == "image_invalid"
    assert limits.check_image("data:image/png;base64,") == "image_invalid"
    monkeypatch.setattr(settings, "chat_max_image_bytes", 16)
    assert limits.check_image(PNG) == "image_too_large"


# ------------------------------------------------------------------- chat rate limits
def test_chat_rate_limit_per_ip_returns_429_with_retry_after(client, fast_chat, monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_ip_per_min", 2)
    assert _chat(client).status_code == 200 and _chat(client).status_code == 200
    r = _chat(client)
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/json")
    assert int(r.headers["retry-after"]) >= 1
    assert r.json() == {"detail": _msg("rate_limited", "en")}
    assert len(fast_chat) == 2  # the third request never reached the agent


@pytest.mark.parametrize("locale", ["fi", "sv"])
def test_chat_rate_limit_message_follows_the_user_language(client, fast_chat, monkeypatch, locale):
    monkeypatch.setattr(settings, "chat_rate_per_ip_per_min", 1)
    assert _chat(client, TEXT[locale], locale=locale).status_code == 200
    r = _chat(client, TEXT[locale], locale=locale)
    assert r.status_code == 429 and r.json()["detail"] == _msg("rate_limited", locale)


def test_chat_rate_limit_per_customer(client, fast_chat, monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_ip_per_min", 0)
    monkeypatch.setattr(settings, "chat_rate_per_customer_per_min", 1)
    assert _chat(client, cid="CUST05020").status_code == 200
    assert _chat(client, cid="CUST05020").status_code == 429
    assert _chat(client, cid="CUST00584").status_code == 200  # another customer is not affected


def test_forwarded_header_from_a_direct_caller_does_not_dodge_the_limit(client, fast_chat, monkeypatch):
    monkeypatch.setattr(settings, "chat_rate_per_ip_per_min", 1)
    assert _chat(client, headers={"X-Forwarded-For": "10.1.1.1"}).status_code == 200
    assert _chat(client, headers={"X-Forwarded-For": "10.2.2.2"}).status_code == 429


def test_unknown_customer_is_404_before_any_stream(client, fast_chat):
    assert _chat(client, cid="CUST99999").status_code == 404 and fast_chat == []


def test_feedback_rate_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "feedback_rate_per_ip_per_min", 2)
    codes = [client.post("/api/chat/feedback", json={"message_id": f"msg_h{i}", "rating": 1}).status_code for i in range(3)]
    assert codes == [200, 200, 429]


# -------------------------------------------------------------------- chat size limits
def _only_event(response) -> tuple[str, dict]:
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert len(events) == 1
    return events[0]


@pytest.mark.parametrize("locale", LOCALES)
def test_too_long_message_is_one_sse_error_in_the_user_language(client, fast_chat, monkeypatch, locale):
    monkeypatch.setattr(settings, "chat_max_message_chars", 200)
    name, data = _only_event(_chat(client, (TEXT[locale] + " ") * 10, locale=locale))
    assert name == "error" and data["message"] == _msg("message_too_long", locale)
    assert "200" in data["message"] and fast_chat == []


def test_too_long_history_is_one_sse_error(client, fast_chat, monkeypatch):
    monkeypatch.setattr(settings, "chat_max_history_messages", 4)
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": "hello there"} for i in range(5)]
    name, data = _only_event(_chat(client, messages=history))
    assert name == "error" and data["message"] == _msg("history_too_long", "en") and fast_chat == []


def test_bad_or_oversized_photo_is_one_sse_error(client, fast_chat, monkeypatch):
    junk = base64.b64encode(b"A" * 300).decode()
    name, data = _only_event(_chat(client, image_base64=junk))
    assert name == "error" and data["message"] == _msg("image_invalid", "en")
    monkeypatch.setattr(settings, "chat_max_image_bytes", 32)
    name, data = _only_event(_chat(client, TEXT["sv"], locale="sv", image_base64=PNG))
    assert name == "error" and data["message"] == _msg("image_too_large", "sv")
    assert fast_chat == []


def test_valid_photo_and_normal_message_pass(client, fast_chat):
    events = parse_sse(_chat(client, image_base64=PNG).text)
    assert events[-1][0] == "done" and fast_chat == [False]


def test_request_body_limit_with_content_length(client, fast_chat, monkeypatch):
    monkeypatch.setattr(settings, "max_body_bytes", 2000)
    r = _chat(client, "a" * 5000)
    assert r.status_code == 413 and r.json() == {"detail": _msg("body_too_large", "en")}
    r = client.post("/api/chat?locale=fi", content=b"a" * 5000, headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json() == {"detail": _msg("body_too_large", "fi")}
    assert fast_chat == []
    assert client.get("/api/health").status_code == 200  # reads are never affected


def test_request_body_limit_without_content_length(client, fast_chat, monkeypatch):
    monkeypatch.setattr(settings, "max_body_bytes", 2000)

    def chunks():
        yield b'{"customer_id":"CUST05020","messages":[{"role":"user","content":"'
        for _ in range(20):
            yield b"a" * 500
        yield b'"}]}'

    r = client.post("/api/chat", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413 and r.json() == {"detail": _msg("body_too_large", "en")}
    assert fast_chat == []


# ------------------------------------------------------------------ LLM concurrency cap
async def test_llm_slots_are_capped_and_released(monkeypatch):
    monkeypatch.setattr(settings, "chat_max_concurrent_llm", 2)
    monkeypatch.setattr(settings, "chat_queue_wait_s", 0.05)
    first, second = await limits.acquire_llm_slot(), await limits.acquire_llm_slot()
    assert first[0] and second[0] and first[1] is second[1]
    assert await limits.acquire_llm_slot() == (False, None)  # full: do not queue forever
    first[1].release()
    free, sem = await limits.acquire_llm_slot()
    assert free and sem is first[1]
    monkeypatch.setattr(settings, "chat_max_concurrent_llm", 0)
    assert await limits.acquire_llm_slot() == (True, None)  # 0 switches the cap off


async def test_llm_slot_waits_briefly_for_a_slot_that_frees_up(monkeypatch):
    monkeypatch.setattr(settings, "chat_max_concurrent_llm", 1)
    monkeypatch.setattr(settings, "chat_queue_wait_s", 2.0)
    _, sem = await limits.acquire_llm_slot()
    asyncio.get_running_loop().call_later(0.05, sem.release)
    assert await limits.acquire_llm_slot() == (True, sem)


class _Slot:
    def __init__(self) -> None:
        self.released = 0

    def release(self) -> None:
        self.released += 1


def test_busy_server_answers_with_the_offline_coach(client, fast_chat, monkeypatch):
    async def busy():
        return False, None

    monkeypatch.setattr(limits, "acquire_llm_slot", busy)
    events = parse_sse(_chat(client).text)
    assert events[-1][0] == "done" and fast_chat == [True]  # force_offline=True


@pytest.mark.parametrize("events, boom", [(None, False), ([ev.token("partial")], True), ([], False), ([ev.token("x")], False)])
def test_stream_always_ends_with_done_or_error_and_frees_the_slot(client, monkeypatch, events, boom):
    import app.routers.chat as chat_mod

    slot = _Slot()

    async def take():
        return True, slot

    monkeypatch.setattr(limits, "acquire_llm_slot", take)
    monkeypatch.setattr(chat_mod, "run_chat", _fake_run(events=events, boom=boom))
    r = _chat(client, TEXT["fi"], locale="fi")
    out = parse_sse(r.text)
    terminal = [name for name, _ in out if name in ("done", "error")]
    assert len(terminal) == 1 and out[-1][0] == terminal[0]
    assert slot.released == 1
    assert "secret internal detail" not in r.text and "Traceback" not in r.text
    if events is not None:  # the agent died or stopped early: a Finnish apology, not silence
        assert out[-1] == ("error", {"message": chat_mod.ERROR_TEXT["fi"]})


# ----------------------------------------------------------------------- health / ready
def test_health_reports_readiness_and_keeps_the_old_fields(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["ready"] is True
    assert body["data"] == {"loaded": True, "state": "ready"}
    assert set(body["llm"]) == {"primary", "fallback", "available"} and all(isinstance(v, bool) for v in body["llm"].values())
    assert body["as_of"] == settings.as_of_date.isoformat()
    r = client.get("/api/ready")
    assert r.status_code == 200 and r.json() == {"ready": True, "data": {"state": "ready"}}


@pytest.mark.parametrize("state, status", [("loading", "starting"), ("error", "degraded")])
def test_health_answers_at_once_while_the_cache_is_not_ready(client, monkeypatch, state, status):
    from app import db

    started: list[int] = []

    def never_block(*_a, **_k):
        raise AssertionError("health must not wait for the ledger cache")

    monkeypatch.setattr(db, "is_ready", lambda: False)
    monkeypatch.setattr(db, "readiness", lambda: state)
    monkeypatch.setattr(db, "start_warmup", lambda: started.append(1))
    monkeypatch.setattr(db, "get_conn", never_block)
    t0 = time.perf_counter()
    r = client.get("/api/health")
    assert time.perf_counter() - t0 < 1.0
    body = r.json()
    assert r.status_code == 200 and body["status"] == status and body["ready"] is False
    assert body["data"] == {"loaded": False, "state": state}
    assert started  # the build is (re)started in the background
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.json() == {"ready": False, "data": {"state": state}}


def test_health_stays_responsive_during_a_slow_first_boot_build(client, fast_chat, monkeypatch):
    """The cache build takes seconds on first boot; health and the event loop must not wait."""
    import threading

    from app import db

    loaded = db.get_conn()
    gate = threading.Event()

    def slow_build():
        gate.wait(20)
        db._conn = loaded
        return loaded

    monkeypatch.setattr(db, "_conn", None)
    monkeypatch.setattr(db, "_warm_thread", None)
    monkeypatch.setattr(db, "get_conn", slow_build)
    db._customer_row.cache_clear()  # as on a fresh boot: the customer lookup needs the data
    db.start_warmup()
    chat_result: list[int] = []
    waiting_chat = threading.Thread(target=lambda: chat_result.append(_chat(client).status_code))
    waiting_chat.start()  # its customer check needs the data and waits in a worker thread
    try:
        time.sleep(0.2)
        for path, code in (("/api/health", 200), ("/api/ready", 503)):
            t0 = time.perf_counter()
            r = client.get(path)
            assert time.perf_counter() - t0 < 1.0 and r.status_code == code
        assert client.get("/api/health").json()["status"] == "starting" and chat_result == []
    finally:
        gate.set()
        waiting_chat.join(10)
        db._warm_thread.join(10)
    assert chat_result == [200]
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["ready"] is True and client.get("/api/ready").status_code == 200


def test_warmup_is_idempotent_and_reports_ready(client):
    from app import db

    db.start_warmup()
    db.start_warmup()
    assert db.is_ready() and db.readiness() == "ready"


def test_health_llm_available_goes_false_while_providers_rest(client, monkeypatch):
    from app.agent import llm as llm_mod

    fake = SimpleNamespace(configured=True, any_healthy=lambda: False)
    monkeypatch.setattr(llm_mod, "get_llm", lambda: fake)
    monkeypatch.delenv("LLM_OFFLINE", raising=False)
    assert client.get("/api/health").json()["llm"]["available"] is False
    fake.any_healthy = lambda: True
    assert client.get("/api/health").json()["llm"]["available"] is True


# -------------------------------------------------------------------------------- CORS
def _preflight(client, origin: str):
    return client.options("/api/chat", headers={"Origin": origin, "Access-Control-Request-Method": "POST",
                                                "Access-Control-Request-Headers": "content-type"})


@pytest.mark.parametrize("origin", ["http://localhost:8081", "http://127.0.0.1:19006", "http://192.168.1.20:8081"])
def test_cors_allows_local_development_origins(client, origin):
    r = _preflight(client, origin)
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in r.headers
    assert client.get("/api/health", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin


@pytest.mark.parametrize("origin", ["https://evil.example", "http://localhost.evil.example", "https://192.168.1.20.evil.example"])
def test_cors_refuses_other_origins_by_default(client, origin):
    if "*" in settings.cors_origins or origin in settings.cors_origins:
        pytest.skip("CORS_ORIGINS is opened up in this environment")
    r = _preflight(client, origin)
    assert r.status_code == 400 and "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in client.get("/api/health", headers={"Origin": origin}).headers


def test_cors_origins_setting_accepts_comma_and_json_lists():
    from app.config import Settings

    assert Settings(_env_file=None, cors_origins="https://a.example, https://b.example").cors_origins == ["https://a.example", "https://b.example"]
    assert Settings(_env_file=None, cors_origins='["https://a.example"]').cors_origins == ["https://a.example"]
    assert Settings.model_fields["cors_origins"].default == []  # not wide open unless configured


# ---------------------------------------------------------------- error bodies (no traces)
@pytest.mark.parametrize("locale", LOCALES)
def test_unexpected_error_is_clean_json_without_internals(monkeypatch, locale):
    from fastapi.testclient import TestClient

    import app.routers.meta as meta
    from app.main import app

    def explode(*_a, **_k):
        raise RuntimeError("boom at /srv/app/secret.py line 12")

    monkeypatch.setattr(meta.content, "get_lessons", explode)
    r = TestClient(app, raise_server_exceptions=False).get(f"/api/lessons?locale={locale}")
    assert r.status_code == 500 and r.json() == {"detail": _msg("server_error", locale)}
    assert "boom" not in r.text and "Traceback" not in r.text and "secret" not in r.text


def test_overflow_is_422_not_500(monkeypatch):
    from fastapi.testclient import TestClient

    import app.routers.meta as meta
    from app.main import app

    def overflow(*_a, **_k):
        raise OverflowError("date value out of range")

    monkeypatch.setattr(meta.content, "get_lessons", overflow)
    r = TestClient(app, raise_server_exceptions=False).get("/api/lessons?locale=sv")
    assert r.status_code == 422 and r.json() == {"detail": _msg("out_of_range", "sv")}


@pytest.mark.parametrize("route", [
    "transactions?offset=9223372036854775807",
    "transactions?start=0001-01-01",
    "spending?end=0001-01-01",
    "spending?start=9999-12-31",
    "survival?until=9999-12-31",
])
def test_absurd_query_values_are_422(client, route):
    r = client.get(f"/api/customers/CUST05020/{route}")
    assert r.status_code == 422 and "detail" in r.json() and "Traceback" not in r.text


@pytest.mark.parametrize("locale, word", [("en", "out of range"), ("fi", "sallitun alueen ulkopuolella"), ("sv", "utanför det tillåtna intervallet")])
def test_date_range_error_is_localised(client, locale, word):
    r = client.get(f"/api/customers/CUST05020/spending?start=9999-12-31&locale={locale}")
    assert r.status_code == 422 and word in json.dumps(r.json(), ensure_ascii=False)


# ------------------------------------------------------------------------------- store
def test_sqlite_uses_wal_and_a_busy_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "state_db", tmp_path / "state.db")
    with store.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == settings.sqlite_busy_timeout_ms == 5000
    monkeypatch.setattr(settings, "sqlite_busy_timeout_ms", 0)
    with store.connect() as conn:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 0


def test_two_workers_starting_together_seed_the_demo_goals_once(tmp_path):
    """Four fresh processes open the same empty state file at the same moment."""
    path = tmp_path / "state.db"
    backend = Path(__file__).resolve().parents[1]
    code = "from app import store; print(len(store.goal_rows('CUST05020')))"
    env = {**os.environ, "STATE_DB": str(path)}
    procs = [subprocess.Popen([sys.executable, "-c", code], cwd=backend, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
             for _ in range(4)]
    outs = [p.communicate(timeout=60) for p in procs]
    assert all(p.returncode == 0 for p in procs), [err[-300:] for _, err in outs]
    expected = len(store.SEED_GOALS["CUST05020"])
    assert {out.strip() for out, _ in outs} == {str(expected)}
    import sqlite3

    conn = sqlite3.connect(path)
    try:
        assert conn.execute("SELECT count(*) FROM goals").fetchone()[0] == sum(len(v) for v in store.SEED_GOALS.values())
    finally:
        conn.close()


def test_a_locked_database_is_waited_for_not_failed(tmp_path, monkeypatch):
    import sqlite3
    import threading

    monkeypatch.setattr(settings, "state_db", tmp_path / "state.db")
    before = store.goal_count("CUST05020")
    blocker = sqlite3.connect(tmp_path / "state.db", isolation_level=None, check_same_thread=False)
    blocker.execute("BEGIN IMMEDIATE")  # another worker is in the middle of a write
    threading.Timer(0.3, lambda: blocker.execute("COMMIT")).start()
    row = store.insert_goal({"customer_id": "CUST05020", "name": "Wait", "emoji": "⏳", "kind": "other",
                             "target_amount": 10.0, "saved_amount": 0.0, "deadline": None, "monthly_contribution": 0.0})
    assert row["name"] == "Wait" and store.goal_count("CUST05020") == before + 1
    blocker.close()
