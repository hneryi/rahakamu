"""LLM layer: streamed tool-call accumulation, think-tag filtering, failover & circuit breaker."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.agent.llm import LLMChunk, LLMClient, LLMUnavailable, ThinkTagFilter, ToolCall, ToolCallAccumulator
from app.agent.settings import AgentSettings, ProviderConfig


def test_accumulates_split_arguments_by_index():
    acc = ToolCallAccumulator()
    acc.add([{"index": 0, "id": "call_a", "type": "function", "function": {"name": "query_spending"}}])
    for frag in ['{"subcategory": "ta', 'xi", "period": "', 'last_month"}']:
        acc.add([{"index": 0, "function": {"arguments": frag}}])
    calls = acc.result()
    assert len(calls) == 1
    assert calls[0].id == "call_a" and calls[0].name == "query_spending"
    assert calls[0].parsed_arguments() == {"subcategory": "taxi", "period": "last_month"}


def test_accumulates_parallel_calls_interleaved():
    acc = ToolCallAccumulator()
    acc.add([{"index": 0, "id": "c0", "function": {"name": "safe_to_spend", "arguments": ""}}, {"index": 1, "id": "c1", "function": {"name": "list_goals"}}])
    acc.add([{"index": 1, "function": {"arguments": "{}"}}, {"index": 0, "function": {"arguments": "{}"}}])
    names = [c.name for c in acc.result()]
    assert names == ["safe_to_spend", "list_goals"]


def test_accumulator_accepts_sdk_objects_and_missing_index():
    fn = SimpleNamespace(name="plan_goal", arguments='{"target_amount": 12000}')
    acc = ToolCallAccumulator()
    acc.add([SimpleNamespace(index=None, id="x1", function=fn)])
    acc.add([SimpleNamespace(index=None, id=None, function=SimpleNamespace(name=None, arguments=""))])
    (call,) = acc.result()
    assert call.parsed_arguments()["target_amount"] == 12000


def test_parsed_arguments_is_lenient():
    assert ToolCall("1", "x", "").parsed_arguments() == {}
    assert ToolCall("1", "x", 'sure: {"a": 1} ').parsed_arguments() == {"a": 1}
    assert ToolCall("1", "x", "not json").parsed_arguments() == {}


@pytest.mark.parametrize(
    "chunks,expected",
    [
        (["Hello ", "world"], "Hello world"),
        (["<think>secret</think>Answer"], "Answer"),
        (["<thi", "nk>hidden", " stuff</th", "ink>Visible"], "Visible"),
        (["a < b and ", "c"], "a < b and c"),
    ],
)
def test_think_filter(chunks, expected):
    f = ThinkTagFilter()
    out = "".join(f.feed(c) for c in chunks) + f.flush()
    assert out == expected


def _settings(n: int = 2) -> AgentSettings:
    providers = tuple(ProviderConfig(name=name, base_url="http://x", model="m", api_key="k") for name in ("primary", "fallback")[:n])
    return AgentSettings(providers=providers, offline=False, thinking=True, as_of=__import__("datetime").date(2026, 9, 18), request_timeout_s=5, first_token_timeout_s=5, unhealthy_cooldown_s=60, max_tool_rounds=6)


class _Err(Exception):
    def __init__(self, status: int):
        super().__init__(f"status {status}")
        self.status_code = status


async def _collect(client: LLMClient):
    return [c async for c in client.stream([{"role": "user", "content": "hi"}])]


async def test_retry_once_then_failover_and_mark_unhealthy(monkeypatch):
    client = LLMClient(_settings())
    attempts: list[str] = []

    async def fake_stream_one(self, state, *args, **kwargs):
        attempts.append(state.config.name)
        if state.config.name == "primary":
            raise ConnectionError("reset")
        yield LLMChunk(kind="content", text="from fallback", provider="fallback")
        yield LLMChunk(kind="done", finish_reason="stop", provider="fallback")

    monkeypatch.setattr(LLMClient, "_stream_one", fake_stream_one)
    chunks = await _collect(client)
    assert attempts == ["primary", "primary", "fallback"]  # one retry, then failover
    assert chunks[0].text == "from fallback"
    assert client.status() == {"primary": False, "fallback": True}
    # next request skips the unhealthy primary entirely
    attempts.clear()
    await _collect(client)
    assert attempts == ["fallback"]


async def test_auth_error_skips_retry_and_raises_when_all_fail(monkeypatch):
    client = LLMClient(_settings())
    attempts: list[str] = []

    async def fake_stream_one(self, state, *args, **kwargs):
        attempts.append(state.config.name)
        raise _Err(403)
        yield  # pragma: no cover

    monkeypatch.setattr(LLMClient, "_stream_one", fake_stream_one)
    with pytest.raises(LLMUnavailable):
        await _collect(client)
    assert attempts == ["primary", "fallback"]  # 403 = no retry
    assert not client.any_healthy()


async def test_bad_request_does_not_mark_unhealthy(monkeypatch):
    client = LLMClient(_settings(1))

    async def fake_stream_one(self, state, *args, **kwargs):
        raise _Err(400)
        yield  # pragma: no cover

    monkeypatch.setattr(LLMClient, "_stream_one", fake_stream_one)
    with pytest.raises(LLMUnavailable):
        await _collect(client)
    assert client.any_healthy()


async def test_cooldown_expires(monkeypatch):
    client = LLMClient(_settings(1))
    client.mark_unhealthy("primary", seconds=0.01)
    assert not client.any_healthy()
    time.sleep(0.02)
    assert client.any_healthy()


def test_api_key_never_in_repr():
    cfg = ProviderConfig(name="primary", base_url="http://x", model="m", api_key="super-secret-key")
    assert "super-secret-key" not in repr(cfg)


# ----------------------------------------------------------- failure classes (hardening)
def _failing(client_attempts: list[str], exc_factory):
    async def fake_stream_one(self, state, *args, **kwargs):
        client_attempts.append(state.config.name)
        if state.config.name == "primary":
            raise exc_factory()
        yield LLMChunk(kind="content", text="from fallback", provider="fallback")
        yield LLMChunk(kind="done", finish_reason="stop", provider="fallback")

    return fake_stream_one


async def test_timeout_is_not_retried(monkeypatch):
    """A hang before the first token must cost one timeout, not two."""
    client = LLMClient(_settings())
    attempts: list[str] = []
    monkeypatch.setattr(LLMClient, "_stream_one", _failing(attempts, TimeoutError))
    await _collect(client)
    assert attempts == ["primary", "fallback"]


async def test_rate_limit_is_not_retried_and_rests_briefly(monkeypatch):
    """One 429 must not open the 60 s breaker for every user of this worker."""
    client = LLMClient(_settings())
    attempts: list[str] = []
    monkeypatch.setattr(LLMClient, "_stream_one", _failing(attempts, lambda: _Err(429)))
    await _collect(client)
    assert attempts == ["primary", "fallback"]
    primary = client._providers[0]
    rest = primary.unhealthy_until - time.monotonic()
    assert 0 < rest <= client.settings.short_cooldown_s + 0.1
    assert primary.failures == 0  # a 429 does not count towards the long breaker


async def test_rate_limit_honours_retry_after_clamped(monkeypatch):
    class _Resp:
        def __init__(self, value):
            self.headers = {"retry-after": value}

    def make(value):
        err = _Err(429)
        err.response = _Resp(value)
        return err

    for header, low, high in (("12", 11, 12.1), ("900", 29, 30.1), ("0", 0.5, 1.1), ("soon", 4, 5.1)):
        client = LLMClient(_settings())
        monkeypatch.setattr(LLMClient, "_stream_one", _failing([], lambda h=header: make(h)))
        await _collect(client)
        rest = client._providers[0].unhealthy_until - time.monotonic()
        assert low <= rest <= high, header


async def test_long_breaker_opens_only_after_repeated_failures(monkeypatch):
    client = LLMClient(_settings())
    monkeypatch.setattr(LLMClient, "_stream_one", _failing([], TimeoutError))
    primary = client._providers[0]
    for expected_failures in (1, 2):
        primary.unhealthy_until = 0.0  # pretend the short rest is over
        await _collect(client)
        assert primary.failures == expected_failures
        assert primary.unhealthy_until - time.monotonic() <= client.settings.short_cooldown_s + 0.1
    primary.unhealthy_until = 0.0
    await _collect(client)
    assert primary.failures == 3
    assert primary.unhealthy_until - time.monotonic() > client.settings.unhealthy_cooldown_s - 1


async def test_success_resets_the_failure_count(monkeypatch):
    client = LLMClient(_settings(1))
    client._providers[0].failures = 2

    async def ok(self, state, *args, **kwargs):
        yield LLMChunk(kind="done", finish_reason="stop", provider="primary")

    monkeypatch.setattr(LLMClient, "_stream_one", ok)
    await _collect(client)
    assert client._providers[0].failures == 0
