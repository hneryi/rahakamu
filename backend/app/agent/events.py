"""Chat request model and SSE event helpers (SPEC §4.2).

The chat endpoint is a one-way stream of small typed events, so the mobile app can
animate the character *while* work happens: ``status`` (thinking → tool → writing),
``tool`` (what was looked up), ``widget`` (generative UI), ``token`` (answer text),
then ``done`` (sources, suggestions, mood) or ``error``.

Keeping the request model and event constructors here (instead of in the router) lets
the orchestrator, the offline fallback, the evals runner and the tests share them
without importing FastAPI.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

EventType = Literal["status", "tool", "widget", "token", "done", "error"]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    #: Hard ceiling only. The friendly, configurable limits (``CHAT_MAX_MESSAGE_CHARS``,
    #: ``CHAT_MAX_HISTORY_MESSAGES``, ``CHAT_MAX_IMAGE_BYTES``) are checked in
    #: ``app.limits.check_chat_request`` so the user gets a message in their own language
    #: instead of a validation error.
    content: str = Field(default="", max_length=100_000)


class ChatRequest(BaseModel):
    """Body of ``POST /api/chat``."""

    customer_id: str = Field(min_length=1, max_length=32)
    persona: str = "sisu"
    locale: str = "en"
    messages: list[ChatMessage] = Field(default_factory=list, max_length=500)
    image_base64: str | None = Field(default=None, max_length=12_000_000)

    @field_validator("persona")
    @classmethod
    def _persona(cls, v: str) -> str:
        v = (v or "sisu").lower()
        return v if v in ("sisu", "aava") else "sisu"

    @field_validator("locale")
    @classmethod
    def _locale(cls, v: str) -> str:
        v = (v or "en").split("-")[0].lower()
        return v if v in ("en", "fi", "sv") else "en"

    @property
    def last_user_text(self) -> str:
        for m in reversed(self.messages):
            if m.role == "user":
                return m.content
        return ""


def json_safe(value: Any) -> Any:
    """Copy of ``value`` with ``NaN`` / ``Infinity`` replaced by ``None``.

    Python would serialise those as bare ``NaN`` / ``Infinity``, which is not JSON:
    ``JSON.parse`` in the app throws and the whole event is lost. They can appear when the
    model passes an absurd number (``1e400``) to a tool.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def dumps(data: dict[str, Any]) -> str:
    """Compact, strictly valid JSON for one SSE ``data:`` line."""
    try:
        return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except ValueError:  # a non-finite float somewhere inside
        return json.dumps(json_safe(data), ensure_ascii=False, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class SSEEvent:
    event: EventType
    data: dict[str, Any]

    def to_sse(self) -> str:
        """Wire format: ``event: <type>\\ndata: <json>\\n\\n`` (one JSON line)."""
        return f"event: {self.event}\ndata: {dumps(self.data)}\n\n"

    def for_sse_starlette(self) -> dict[str, str]:
        return {"event": self.event, "data": dumps(self.data)}


def status(state: Literal["thinking", "tool", "writing"], label: str) -> SSEEvent:
    return SSEEvent("status", {"state": state, "label": label})


def tool_event(name: str, args: dict[str, Any], summary: str) -> SSEEvent:
    return SSEEvent("tool", {"name": name, "args": args, "summary": summary})


def widget_event(widget: dict[str, Any]) -> SSEEvent:
    return SSEEvent("widget", {"id": widget["id"], "type": widget["type"], "data": widget["data"]})


def token(text: str) -> SSEEvent:
    return SSEEvent("token", {"text": text})


def done(
    message_id: str,
    sources: dict[str, Any],
    suggestions: list[str],
    mood: str,
    *,
    truncated: bool = False,
    guardrail: str | None = None,
) -> SSEEvent:
    """Final event of a successful turn.

    Two optional, additive fields (absent on a normal turn): ``truncated: true`` when the
    model connection dropped before the answer was complete, and ``guardrail`` (a short
    code such as ``"ungrounded_amount"`` or ``"investment_pick"``) when the answer was
    corrected by the post-check in the orchestrator.
    """
    data: dict[str, Any] = {"message_id": message_id, "sources": sources, "suggestions": suggestions, "mood": mood}
    if truncated:
        data["truncated"] = True
    if guardrail:
        data["guardrail"] = guardrail
    return SSEEvent("done", data)


def error(message: str) -> SSEEvent:
    return SSEEvent("error", {"message": message})


def parse_sse(text: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE text stream back into ``(event, data)`` tuples (tests, evals, clients)."""
    out: list[tuple[str, dict[str, Any]]] = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        ev, data_lines = "message", []
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        if data_lines:
            try:
                out.append((ev, json.loads("\n".join(data_lines))))
            except json.JSONDecodeError:
                continue
    return out
