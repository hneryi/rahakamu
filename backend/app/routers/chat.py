"""Chat endpoints: ``POST /chat`` (SSE stream) and ``POST /chat/feedback``.

Mounted by ``app.main`` under ``/api``. The router is deliberately thin: validation via
pydantic, then it relays the orchestrator's async generator as Server-Sent Events.

Why SSE (and not WebSockets)?
SSE is plain HTTP: it passes through corporate proxies, CDNs and the S-mobiili WebView
without special infrastructure, works with ``fetch`` streaming on React Native
(``expo/fetch``) and in browsers, and maps perfectly onto a one-request/one-answer chat
turn. ``sse-starlette`` adds keep-alive pings so mobile networks do not drop idle streams
while the model is thinking.

Feedback (👍/👎) is stored through ``app.store.save_feedback`` when available; otherwise
it is appended to ``backend/feedback.jsonl`` so it is never lost during a demo.

Public-demo protection (details and defaults in :mod:`app.limits`):

* per-IP and per-customer rate limits → ``429 {"detail": …}`` with ``Retry-After``;
* message / history / photo size limits → a normal SSE stream holding one ``error`` event
  in the user's language (the app shows SSE error text as a chat bubble);
* at most ``CHAT_MAX_CONCURRENT_LLM`` turns use the model at once; a turn that finds no
  free slot is answered by the offline coach instead of waiting;
* every stream ends with exactly one ``done`` or ``error`` event.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app import limits
from app.agent import events as ev
from app.agent.events import ChatRequest
from app.agent.orchestrator import ERROR_TEXT, run_chat, turn_language
from app.config import settings
from app.i18n import use_locale

log = logging.getLogger("spankkibot.chat")

router = APIRouter(tags=["chat"])

FEEDBACK_FALLBACK_PATH = Path(__file__).resolve().parents[2] / "feedback.jsonl"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> EventSourceResponse:
    """Stream one assistant turn as SSE events: status, tool, widget, token, done | error."""
    language = turn_language(req)
    with use_locale(language):  # limit messages in the language of the user's message
        blocked = limits.too_many(limits.chat_ip_limiter, limits.client_ip(request), settings.chat_rate_per_ip_per_min)
        if blocked:
            raise blocked
        # In a worker thread: on first boot this waits for the ledger cache, and the event
        # loop (health checks, other streams) must stay responsive meanwhile.
        await asyncio.to_thread(_ensure_customer, req.customer_id)
        blocked = limits.too_many(limits.chat_customer_limiter, req.customer_id, settings.chat_rate_per_customer_per_min)
        if blocked:
            raise blocked
        problem = limits.check_chat_request(req)
        problem_text = limits.message(problem) if problem else None

    async def event_source():  # noqa: ANN202 - async generator of sse dicts
        finished = False  # a done / error event went out
        gone = False  # the client hung up
        slot = None
        try:
            if problem_text:
                finished = True
                yield ev.error(problem_text).for_sse_starlette()
                return
            free, slot = await limits.acquire_llm_slot()
            if not free:
                log.warning("All %d LLM slots busy; answering offline", settings.chat_max_concurrent_llm)
            async for event in run_chat(req, force_offline=not free):
                if await request.is_disconnected():
                    log.info("Client disconnected; stopping chat stream")
                    gone = True
                    break
                if event.event in ("done", "error"):
                    finished = True
                yield event.for_sse_starlette()
                if finished:
                    break
        except Exception:  # noqa: BLE001 - surface as SSE error, never a broken stream
            log.exception("chat stream failed")
        finally:
            if slot is not None:
                slot.release()
        if not finished and not gone:  # whatever happened, the app must not wait forever
            yield ev.error(ERROR_TEXT[language]).for_sse_starlette()

    return EventSourceResponse(
        event_source(),
        ping=15,
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _ensure_customer(customer_id: str) -> None:
    """Fail fast with 404 for unknown customers (before the stream starts)."""
    try:
        from app import db
    except Exception:  # noqa: BLE001 - data layer unavailable: let tools report it
        return
    check = getattr(db, "ensure_customer", None)
    if not callable(check):
        return
    try:
        check(customer_id)
    except getattr(db, "CustomerNotFound", KeyError) as exc:
        raise HTTPException(status_code=404, detail=f"Unknown customer {customer_id}") from exc
    except Exception:  # noqa: BLE001 - e.g. data still loading; tools degrade gracefully
        log.warning("Customer check failed for %s", customer_id, exc_info=True)


class FeedbackRequest(BaseModel):
    message_id: str = Field(min_length=1, max_length=64)
    rating: int = Field(description="1 = 👍, -1 = 👎")
    comment: str | None = Field(default=None, max_length=2000)
    customer_id: str | None = Field(default=None, max_length=32)
    persona: str | None = Field(default=None, max_length=16)


@router.post("/chat/feedback")
async def chat_feedback(body: FeedbackRequest, request: Request) -> dict[str, Any]:
    """Record a thumbs up/down on an assistant message (used to improve prompts & evals)."""
    blocked = limits.too_many(limits.feedback_ip_limiter, limits.client_ip(request), settings.feedback_rate_per_ip_per_min)
    if blocked:
        raise blocked
    if body.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating must be 1 or -1")
    try:
        from app import store

        save = getattr(store, "save_feedback", None)
        if callable(save):
            return save(body.message_id, body.rating, body.comment, customer_id=body.customer_id, persona=body.persona)
    except Exception:  # noqa: BLE001 - fall back to the JSONL file
        log.warning("store.save_feedback unavailable; writing feedback to JSONL", exc_info=True)
    record = {**body.model_dump(), "created_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with FEEDBACK_FALLBACK_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"ok": True, "message_id": body.message_id, "rating": body.rating}
