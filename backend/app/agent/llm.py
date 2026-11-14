"""Resilient OpenAI-compatible LLM client with a provider chain.

Why this design
---------------
* **Open weights, swappable provider.** We talk to Nemotron 3.5 Super VL through the
  OpenAI chat-completions protocol, so S-Bank could self-host the same model (EU data
  residency) or swap vendors by changing two env vars. Nothing here is vendor-specific
  except an optional vLLM ``chat_template_kwargs`` switch for hybrid reasoning.
* **Streaming with tools.** Tool calls arrive as *deltas*: the first chunk carries the
  call ``id`` and function ``name``; later chunks append fragments of the JSON
  ``arguments`` string, keyed by ``index``. :class:`ToolCallAccumulator` stitches these
  together (and tolerates servers that send whole calls at once, or repeat the id).
* **Reasoning never leaks.** Nemotron returns its chain of thought in a separate
  ``reasoning`` (or ``reasoning_content``) delta field. We surface only the *fact* that
  the model is thinking (``LLMChunk(kind="reasoning")`` without text is what the
  orchestrator uses to show a "thinking" status) and drop the text itself. A
  :class:`ThinkTagFilter` also strips inline ``<think>…</think>`` blocks, which some
  servers emit inside ``content``.
* **Fail fast, fail soft.** Each provider gets a connect/read timeout and a first-chunk
  timeout. What happens after a failure depends on what failed:

  - connection error or 5xx *before anything was streamed*: one retry (retrying after
    tokens reached the user would duplicate text);
  - timeout: no retry, because a second wait would double the user's waiting time;
  - ``429``: no retry; the provider rests for its ``Retry-After`` (1-30 s) or
    ``LLM_SHORT_COOLDOWN_S``, and the request moves to the next provider;
  - ``401/402/403/404`` (bad key, no subscription, no model): 10 minute cooldown;
  - ``400/413/422`` (this request is bad for this provider): no cooldown at all.

  A failed provider rests for ``LLM_SHORT_COOLDOWN_S`` (5 s). Only after
  ``LLM_BREAKER_THRESHOLD`` (3) failures in a row does the long
  ``LLM_UNHEALTHY_COOLDOWN_S`` (60 s) circuit breaker open, so one hiccup does not send
  every user of this worker to the offline coach for a minute. While a provider rests,
  requests go straight to the next provider or to the offline rule-based fallback
  instead of waiting on timeouts. Any success resets the count.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from app.agent.settings import AgentSettings, ProviderConfig, get_settings

log = logging.getLogger("spankkibot.llm")

#: Cooldown for errors that will not fix themselves quickly (bad key, no subscription).
AUTH_COOLDOWN_S = 600.0


class LLMUnavailable(RuntimeError):
    """Raised when every provider in the chain failed before producing output."""


class LLMStreamInterrupted(RuntimeError):
    """Raised when a provider failed *after* some output was already yielded."""


# --------------------------------------------------------------------------- data types


@dataclass
class ToolCall:
    """A fully accumulated tool call from the model."""

    id: str
    name: str
    arguments: str  # raw JSON string as produced by the model

    def parsed_arguments(self) -> dict[str, Any]:
        """Parse ``arguments`` leniently; models occasionally emit '' or trailing junk."""
        raw = (self.arguments or "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            # Try trimming to the outermost JSON object.
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end > start:
                try:
                    value = json.loads(raw[start : end + 1])
                    return value if isinstance(value, dict) else {}
                except json.JSONDecodeError:
                    pass
            log.warning("Unparseable tool arguments for %s", self.name)
            return {}

    def to_message(self) -> dict[str, Any]:
        """OpenAI ``assistant.tool_calls[]`` entry for the conversation history."""
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments or "{}"},
        }


@dataclass
class _PartialCall:
    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


class ToolCallAccumulator:
    """Accumulates streamed ``delta.tool_calls`` fragments into complete calls.

    Accepts either SDK objects or plain dicts (useful in tests). Fragments are keyed by
    ``index``; when a server omits ``index`` we fall back to the call ``id`` or to "the
    last call".
    """

    def __init__(self) -> None:
        self._calls: dict[int, _PartialCall] = {}
        self._order: list[int] = []

    @staticmethod
    def _get(obj: Any, key: str) -> Any:
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(key)
        return getattr(obj, key, None)

    def add(self, deltas: Sequence[Any] | None) -> None:
        for delta in deltas or ():
            index = self._get(delta, "index")
            call_id = self._get(delta, "id")
            if index is None:
                index = next(
                    (i for i, c in self._calls.items() if call_id and c.id == call_id),
                    self._order[-1] if (self._order and not call_id) else len(self._order),
                )
            if index not in self._calls:
                self._calls[index] = _PartialCall()
                self._order.append(index)
            part = self._calls[index]
            if call_id and not part.id:
                part.id = call_id
            fn = self._get(delta, "function")
            name = self._get(fn, "name")
            if name:
                # Some servers resend the full name on every chunk; others split it.
                if not part.name or name.startswith(part.name):
                    part.name = name if len(name) >= len(part.name) else part.name
                else:
                    part.name += name
            args = self._get(fn, "arguments")
            if args:
                part.arguments.append(args)

    def __bool__(self) -> bool:
        return bool(self._calls)

    def result(self) -> list[ToolCall]:
        calls: list[ToolCall] = []
        for n, index in enumerate(self._order):
            part = self._calls[index]
            if not part.name:
                continue
            calls.append(
                ToolCall(
                    id=part.id or f"call_{n}_{int(time.time() * 1000)}",
                    name=part.name,
                    arguments="".join(part.arguments),
                )
            )
        return calls


class ThinkTagFilter:
    """Streaming filter that removes ``<think>…</think>`` spans from content deltas.

    Tags may be split across chunks, so we hold back a short tail that could be the
    beginning of a tag until the next chunk disambiguates it.
    """

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._inside = False
        self._buffer = ""

    def feed(self, text: str) -> str:
        self._buffer += text
        out: list[str] = []
        while self._buffer:
            if self._inside:
                end = self._buffer.find(self.CLOSE)
                if end == -1:
                    # keep a possible partial closing tag
                    keep = self._partial_suffix(self._buffer, self.CLOSE)
                    self._buffer = self._buffer[len(self._buffer) - keep :] if keep else ""
                    break
                self._buffer = self._buffer[end + len(self.CLOSE) :]
                self._inside = False
            else:
                start = self._buffer.find(self.OPEN)
                if start == -1:
                    keep = self._partial_suffix(self._buffer, self.OPEN)
                    emit = self._buffer[: len(self._buffer) - keep]
                    out.append(emit)
                    self._buffer = self._buffer[len(emit) :]
                    break
                out.append(self._buffer[:start])
                self._buffer = self._buffer[start + len(self.OPEN) :]
                self._inside = True
        return "".join(out)

    def flush(self) -> str:
        rest = "" if self._inside else self._buffer
        self._buffer = ""
        return rest

    @staticmethod
    def _partial_suffix(text: str, tag: str) -> int:
        for k in range(min(len(tag) - 1, len(text)), 0, -1):
            if text.endswith(tag[:k]):
                return k
        return 0


@dataclass
class LLMChunk:
    """One normalised streaming event from the provider chain.

    kind:
      * ``reasoning`` – the model is thinking (text intentionally omitted)
      * ``content``   – user-visible answer text (already think-tag filtered)
      * ``tool_calls``– the round ended with these complete tool calls
      * ``done``      – the round ended; ``finish_reason`` set, ``provider`` names the endpoint
    """

    kind: Literal["reasoning", "content", "tool_calls", "done"]
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    provider: str = ""


# --------------------------------------------------------------------------- provider chain


@dataclass
class _ProviderState:
    config: ProviderConfig
    unhealthy_until: float = 0.0
    last_error: str = ""
    client: Any = None
    failures: int = 0  # consecutive failures; reset by any successful round

    @property
    def healthy(self) -> bool:
        return time.monotonic() >= self.unhealthy_until


class LLMClient:
    """Streams chat completions through the configured provider chain."""

    def __init__(self, settings: AgentSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._providers = [_ProviderState(cfg) for cfg in self.settings.providers]

    # -- health -----------------------------------------------------------------------
    @property
    def configured(self) -> bool:
        return bool(self._providers)

    def any_healthy(self) -> bool:
        return any(p.healthy for p in self._providers)

    def status(self) -> dict[str, bool]:
        """``{"primary": bool, "fallback": bool}`` for ``GET /api/health``."""
        out = {"primary": False}
        for p in self._providers:
            out[p.config.name] = p.healthy
        return out

    def mark_unhealthy(self, name: str, seconds: float | None = None, reason: str = "") -> None:
        for p in self._providers:
            if p.config.name == name:
                p.unhealthy_until = time.monotonic() + (
                    seconds if seconds is not None else self.settings.unhealthy_cooldown_s
                )
                p.last_error = reason[:200]

    def _note_failure(self, state: _ProviderState, reason: str) -> None:
        """Count a failure: short rest first, the long breaker after repeated failures."""
        state.failures += 1
        if state.failures >= self.settings.breaker_threshold:
            self.mark_unhealthy(state.config.name, reason=reason)
            log.warning("LLM provider %s marked unhealthy after %d failures: %s",
                        state.config.name, state.failures, reason)
        else:
            self.mark_unhealthy(state.config.name, self.settings.short_cooldown_s, reason)
            log.warning("LLM provider %s failed (%s); resting %.0f s",
                        state.config.name, reason, self.settings.short_cooldown_s)

    def _client(self, state: _ProviderState) -> Any:
        if state.client is None:
            from openai import AsyncOpenAI

            timeout = httpx.Timeout(self.settings.request_timeout_s, connect=5.0)
            state.client = AsyncOpenAI(
                base_url=state.config.base_url,
                api_key=state.config.api_key,
                timeout=timeout,
                max_retries=0,  # we implement our own single retry + failover
            )
        return state.client

    # -- streaming --------------------------------------------------------------------
    async def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        tool_choice: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        thinking: bool | None = None,
    ) -> AsyncIterator[LLMChunk]:
        """Yield :class:`LLMChunk` events for one model round.

        ``thinking`` overrides ``LLM_THINKING`` for hybrid reasoning models: the
        orchestrator thinks while *choosing tools* (date maths, which filter) but writes
        the final answer without a reasoning pass, which halves latency and avoids the
        reasoning eating the whole token budget.

        Tries each healthy provider in order; retries a provider once if it fails
        before yielding anything. Raises :class:`LLMUnavailable` if nothing worked, or
        :class:`LLMStreamInterrupted` if a provider died mid-answer.
        """
        errors: list[str] = []
        candidates = [p for p in self._providers if p.healthy]
        for state in candidates:
            for attempt in range(2):
                yielded = False
                try:
                    async for chunk in self._stream_one(
                        state, messages, tools, tool_choice, temperature, max_tokens, thinking
                    ):
                        yielded = True
                        yield chunk
                    state.failures = 0
                    return
                except LLMStreamInterrupted:
                    raise
                except Exception as exc:  # noqa: BLE001 - classify below
                    reason = _describe_error(exc)
                    errors.append(f"{state.config.name}: {reason}")
                    if yielded:
                        self._note_failure(state, reason)
                        raise LLMStreamInterrupted(reason) from exc
                    if _is_auth_error(exc):
                        self.mark_unhealthy(state.config.name, AUTH_COOLDOWN_S, reason)
                        log.warning("LLM provider %s unavailable: %s", state.config.name, reason)
                        break
                    if _is_request_error(exc):
                        # This request is bad for this provider (e.g. image unsupported,
                        # context too long). Do not punish the provider; try the next one.
                        log.warning("LLM provider %s rejected request: %s", state.config.name, reason)
                        break
                    if _is_rate_limited(exc):
                        # The provider asks us to slow down: retrying at once only adds
                        # load. Rest briefly (not the long breaker) and move on.
                        rest = _retry_after_s(exc, self.settings.short_cooldown_s)
                        self.mark_unhealthy(state.config.name, rest, reason)
                        log.warning("LLM provider %s rate limited; resting %.0f s", state.config.name, rest)
                        break
                    if attempt == 0 and not _is_timeout(exc):
                        log.info("LLM provider %s failed (%s); retrying once", state.config.name, reason)
                        await asyncio.sleep(0.3)
                        continue
                    self._note_failure(state, reason)
                    break
        raise LLMUnavailable("; ".join(errors) or "no healthy LLM provider configured")

    async def _stream_one(
        self,
        state: _ProviderState,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        temperature: float,
        max_tokens: int,
        thinking: bool | None = None,
    ) -> AsyncIterator[LLMChunk]:
        client = self._client(state)
        kwargs: dict[str, Any] = {
            "model": state.config.model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
        if state.config.supports_thinking_toggle:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {
                    "enable_thinking": self.settings.thinking if thinking is None else thinking
                }
            }

        stream = await asyncio.wait_for(
            client.chat.completions.create(**kwargs), timeout=self.settings.first_token_timeout_s
        )
        accumulator = ToolCallAccumulator()
        think_filter = ThinkTagFilter()
        finish_reason: str | None = None
        iterator = stream.__aiter__()
        idle_timeout = self.settings.first_token_timeout_s
        announced_reasoning = False
        while True:
            try:
                chunk = await asyncio.wait_for(iterator.__anext__(), timeout=idle_timeout)
            except StopAsyncIteration:
                break
            if not getattr(chunk, "choices", None):
                continue
            choice = chunk.choices[0]
            delta = choice.delta
            if delta is not None:
                reasoning = getattr(delta, "reasoning", None) or getattr(
                    delta, "reasoning_content", None
                )
                if reasoning is None and getattr(delta, "model_extra", None):
                    extra = delta.model_extra or {}
                    reasoning = extra.get("reasoning") or extra.get("reasoning_content")
                if reasoning and not announced_reasoning:
                    announced_reasoning = True
                    yield LLMChunk(kind="reasoning", provider=state.config.name)
                if delta.content:
                    visible = think_filter.feed(delta.content)
                    if visible:
                        yield LLMChunk(kind="content", text=visible, provider=state.config.name)
                if delta.tool_calls:
                    accumulator.add(delta.tool_calls)
            if choice.finish_reason:
                finish_reason = choice.finish_reason
        tail = think_filter.flush()
        if tail:
            yield LLMChunk(kind="content", text=tail, provider=state.config.name)
        if accumulator:
            yield LLMChunk(
                kind="tool_calls",
                tool_calls=accumulator.result(),
                finish_reason=finish_reason,
                provider=state.config.name,
            )
        yield LLMChunk(kind="done", finish_reason=finish_reason, provider=state.config.name)

    async def complete(
        self, messages: list[dict[str, Any]], *, temperature: float = 0.2, max_tokens: int = 300
    ) -> str:
        """Non-tool convenience call returning the full visible text (used by evals)."""
        parts: list[str] = []
        async for chunk in self.stream(messages, None, temperature=temperature, max_tokens=max_tokens):
            if chunk.kind == "content":
                parts.append(chunk.text)
        return "".join(parts).strip()


def _describe_error(exc: BaseException) -> str:
    """Short, key-free error description safe for logs."""
    status = getattr(exc, "status_code", None)
    name = type(exc).__name__
    if _is_timeout(exc):
        return "timeout"
    body = getattr(exc, "body", None)
    code = ""
    if isinstance(body, dict):
        err = body.get("error", body)
        if isinstance(err, dict):
            code = str(err.get("code") or err.get("type") or "")
        elif isinstance(err, str):
            code = err[:60]
    return f"{name}{f' {status}' if status else ''}{f' {code}' if code else ''}"


def _is_auth_error(exc: BaseException) -> bool:
    """Provider-level errors a retry will not fix soon: bad key, no subscription, no model."""
    return getattr(exc, "status_code", None) in {401, 402, 403, 404}


def _is_request_error(exc: BaseException) -> bool:
    """Request-level rejections (bad payload for this provider); skip without cooldown."""
    return getattr(exc, "status_code", None) in {400, 413, 422}


def _is_rate_limited(exc: BaseException) -> bool:
    return getattr(exc, "status_code", None) == 429


def _is_timeout(exc: BaseException) -> bool:
    """Our own first-chunk / idle timeout or the HTTP client's (``APITimeoutError``)."""
    return isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)) or "Timeout" in type(exc).__name__


def _retry_after_s(exc: BaseException, default: float) -> float:
    """Seconds the provider asked us to wait (``Retry-After``), clamped to 1-30 s."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    try:
        value = float(headers.get("retry-after")) if headers is not None else None
    except (TypeError, ValueError):
        value = None
    if value is None:
        return default
    return min(30.0, max(1.0, value))


_client_singleton: LLMClient | None = None


def get_llm() -> LLMClient:
    """Process-wide client so the circuit-breaker state is shared across requests."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton


def reset_llm() -> None:
    """Drop the singleton (tests / settings reload)."""
    global _client_singleton
    _client_singleton = None
    get_settings.cache_clear()


def llm_status() -> dict[str, bool]:
    """Health summary for ``GET /api/health``: ``{"primary": bool, ...}``."""
    client = get_llm()
    if not client.configured:
        return {"primary": False}
    return client.status()
