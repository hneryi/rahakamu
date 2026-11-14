"""The agent loop behind ``POST /api/chat`` — an async generator of SSE events.

Flow (SPEC §4.2)::

    status(thinking) ─► [LLM round ─► tool calls? ─► status(tool) ─► execute ─► widget* ─► tool]×≤6
                     ─► status(writing) ─► token* ─► done(sources, suggestions, mood)

Design decisions
----------------
* **Stateless.** Every request carries the visible conversation; tool results are not
  replayed from earlier turns. That keeps the service horizontally scalable and easy to
  embed in S-mobiili (no session store), and limits what data sits in prompts.
* **Bounded tool loop.** At most ``LLM_MAX_TOOL_ROUNDS`` (6) rounds. On the last round
  tools are disabled (``tool_choice="none"``) so the model must answer. Identical repeat
  calls are served from a per-request cache so a looping model cannot spam widgets.
* **Generative UI first.** Widgets are emitted as soon as each tool finishes, before the
  text answer streams, so the chart appears while the character is still "talking".
* **Graceful degradation.** If every LLM provider is down (or ``LLM_OFFLINE=1``, or all
  LLM slots are busy), the offline intent router in :mod:`app.agent.fallback` answers
  with the same tools and widgets. If the model fails *after* tools ran, we compose the
  answer from those results; if it returns an empty answer, likewise. If the connection
  drops in the middle of the text, the user is told so (and ``done.truncated`` is set)
  instead of being left with half a sentence. The user always gets an answer.
* **Bounded prompts.** History is cut to the last ``MAX_HISTORY_MESSAGES`` messages and
  ``CHAT_HISTORY_CHAR_BUDGET`` characters; a photo is sent to the model in the first
  ``IMAGE_ROUNDS`` rounds only, so a looping model cannot re-upload megabytes six times.
* **Checked answers.** :mod:`app.agent.guardrails` reviews the finished text for euro
  amounts that no tool produced and for buy / sell picks of named securities.
* **No reasoning leakage.** Reasoning deltas only flip the status to "thinking".
* **One language per turn.** ``turn_language`` detects the language of the user's latest
  message (en / fi / sv; the request ``locale`` decides for "ok"-style messages). That
  single value drives the system prompt, status labels, tool widgets, sources chip,
  follow-up chips and the offline fallback, so a turn never mixes languages.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from typing import Any

from app.agent import events as ev
from app.agent import guardrails
from app.agent.events import ChatRequest, SSEEvent
from app.agent.followups import derive_mood, merge_sources, suggest_followups
from app.agent.lang import detect_language, norm_locale, pick
from app.agent.llm import LLMClient, LLMStreamInterrupted, LLMUnavailable, get_llm
from app.agent.personas import get_persona
from app.agent.prompts import build_system_prompt, build_user_context
from app.agent.settings import get_settings
from app.agent.tools import TOOL_SCHEMAS, ToolContext, ToolResult, execute_tool, status_label

log = logging.getLogger("spankkibot.orchestrator")

MAX_HISTORY_MESSAGES = 12
#: LLM rounds that carry the user's photo (tool choice + the answer of a normal turn).
IMAGE_ROUNDS = 2
INTERRUPTED_TEXT = {
    "en": "(The connection to the AI dropped before I could finish. Please ask again.)",
    "fi": "(Yhteys tekoälyyn katkesi ennen kuin ehdin vastata loppuun. Kysy uudelleen.)",
    "sv": "(Anslutningen till AI:n bröts innan jag hann svara klart. Fråga igen.)",
}
WRITING_LABEL = {"en": "Writing…", "fi": "Kirjoitan…", "sv": "Skriver…"}
ERROR_TEXT = {
    "en": "Sorry, something went wrong. Please try again.",
    "fi": "Pahoittelut, jokin meni pieleen. Yritä uudelleen.",
    "sv": "Förlåt, något gick fel. Försök igen.",
}


def turn_language(req: ChatRequest) -> str:
    """Language for this turn: the user's latest message decides, else the app locale."""
    return detect_language(req.last_user_text, norm_locale(req.locale))


def offline_forced() -> bool:
    """``LLM_OFFLINE=1`` forces the rule-based path (read live so tests can toggle it)."""
    raw = os.environ.get("LLM_OFFLINE")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    return get_settings().offline


def image_content_part(image_base64: str) -> dict[str, Any]:
    """Turn raw base64 (or a data URI) into an OpenAI ``image_url`` content part."""
    data = image_base64.strip()
    if data.startswith("data:"):
        return {"type": "image_url", "image_url": {"url": data}}
    head = data[:16]
    mime = "image/jpeg"
    if head.startswith("iVBOR"):
        mime = "image/png"
    elif head.startswith("UklGR"):
        mime = "image/webp"
    elif head.startswith("R0lGOD"):
        mime = "image/gif"
    try:  # validate quickly; a broken payload should not reach the model
        base64.b64decode(data[:64] + "=" * (-len(data[:64]) % 4), validate=False)
    except Exception:  # noqa: BLE001
        pass
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def _char_budget() -> int:
    try:
        from app.config import settings as app_settings

        return int(app_settings.chat_history_char_budget)
    except Exception:  # noqa: BLE001 - agent package also runs without the app config
        return 12_000


def _history(req: ChatRequest, has_image: bool, locale: str = "en") -> list[dict[str, Any]]:
    msgs = [m for m in req.messages if m.content.strip() or m.role == "user"][-MAX_HISTORY_MESSAGES:]
    budget = _char_budget()
    if budget > 0:  # newest first: keep what fits, always keep the latest message
        kept, used = [], 0
        for m in reversed(msgs):
            used += len(m.content)
            if kept and used > budget:
                break
            kept.append(m)
        msgs = kept[::-1]
    out: list[dict[str, Any]] = [{"role": m.role, "content": m.content} for m in msgs]
    # the conversation must end with a user turn
    if not out or out[-1]["role"] != "user":
        out.append({"role": "user", "content": ""})
    if has_image and req.image_base64:
        text = out[-1]["content"] or pick(locale, "Can I afford this?", "Onko minulla varaa tähän?", "Har jag råd med det här?")
        out[-1] = {"role": "user", "content": [{"type": "text", "text": text}, image_content_part(req.image_base64)]}
    elif not out[-1]["content"]:
        out[-1]["content"] = pick(locale, "Hi!", "Hei!", "Hej!")
    return out


def _args_key(name: str, args: dict[str, Any]) -> str:
    return name + json.dumps(args, sort_keys=True, ensure_ascii=False)


def _drop_image(messages: list[dict[str, Any]], locale: str) -> None:
    """Replace image parts with a short note (the model has already seen the photo)."""
    note = pick(locale, "[The photo was attached earlier in this turn.]", "[Kuva oli liitteenä aiemmin tässä vuorossa.]",
                "[Bilden bifogades tidigare i den här turen.]")
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list) and any(part.get("type") == "image_url" for part in content):
            text = " ".join(part.get("text", "") for part in content if part.get("type") == "text").strip()
            msg["content"] = f"{text}\n{note}" if text else note


async def run_chat(
    req: ChatRequest,
    *,
    llm: LLMClient | None = None,
    trace: dict[str, Any] | None = None,
    force_offline: bool = False,
) -> AsyncIterator[SSEEvent]:
    """Yield the SSE events for one chat turn. Never raises; errors become events.

    ``trace`` (optional, used by evals/tests) receives ``results`` – the list of
    ``(tool_name, ToolResult)`` – ``context`` (the user-context text the model saw) and
    ``mode`` ("llm" | "offline"). ``force_offline`` answers with the rule-based coach
    without calling a model (the chat router uses it when every LLM slot is busy).
    """
    if trace is not None:
        trace.setdefault("results", [])
        trace.setdefault("context", "")
        trace["mode"] = "llm"
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    persona = get_persona(req.persona)
    locale = turn_language(req)
    if trace is not None:
        trace["locale"] = locale
    settings = get_settings()
    ctx = ToolContext(customer_id=req.customer_id, locale=locale, persona=persona.id, as_of=settings.as_of, user_text=req.last_user_text)
    client = llm or get_llm()

    thinking_label = persona.text("status.thinking", locale, "Thinking…")
    yield ev.status("thinking", thinking_label)

    if force_offline or offline_forced() or not client.configured or not client.any_healthy():
        from app.agent.fallback import run_fallback

        if trace is not None:
            trace["mode"] = "offline"
        async for event in run_fallback(req, ctx, message_id=message_id, trace=trace):
            yield event
        return

    has_image = bool(req.image_base64)
    user_ctx = await build_user_context(req.customer_id, settings.as_of, locale)
    system = build_system_prompt(persona, locale, user_ctx, has_image=has_image)
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}, *_history(req, has_image, locale)]

    results: list[tuple[str, ToolResult]] = trace["results"] if trace is not None else []
    if trace is not None:
        trace["context"] = user_ctx.render()
    cache: dict[str, ToolResult] = {}
    answer_parts: list[str] = []
    last_status = thinking_label
    truncated = False

    try:
        round_no = 0
        retried_length = False
        while round_no < settings.max_tool_rounds:
            final_round = round_no == settings.max_tool_rounds - 1
            if has_image and round_no == IMAGE_ROUNDS:
                _drop_image(messages, locale)
            round_text: list[str] = []
            tool_calls = []
            finish_reason: str | None = None
            # Think while choosing tools; answer without a reasoning pass once data is in
            # (faster, and reasoning can no longer exhaust the answer's token budget).
            use_thinking = settings.thinking and not results and not retried_length
            async for chunk in client.stream(
                messages,
                TOOL_SCHEMAS,
                tool_choice="none" if final_round else "auto",
                temperature=0.3,
                thinking=use_thinking,
            ):
                if chunk.kind == "reasoning":
                    label = persona.text("status.thinking", locale, "Thinking…")
                    if last_status != label:
                        last_status = label
                        yield ev.status("thinking", label)
                elif chunk.kind == "content":
                    if not round_text and not answer_parts:
                        label = persona.text("status.writing", locale, WRITING_LABEL[locale])
                        last_status = label
                        yield ev.status("writing", label)
                    round_text.append(chunk.text)
                    answer_parts.append(chunk.text)
                    yield ev.token(chunk.text)
                elif chunk.kind == "tool_calls":
                    tool_calls = chunk.tool_calls
                elif chunk.kind == "done":
                    finish_reason = chunk.finish_reason
            if not tool_calls:
                if not round_text and finish_reason == "length" and not retried_length:
                    # Reasoning used the whole budget without an answer: retry without it.
                    retried_length = True
                    continue
                break
            round_no += 1
            if round_text and not "".join(round_text).endswith("\n\n"):
                # The model spoke before calling tools ("Let me check…"); keep paragraphs apart.
                sep = "\n" if "".join(round_text).endswith("\n") else "\n\n"
                answer_parts.append(sep)
                yield ev.token(sep)
            messages.append({"role": "assistant", "content": "".join(round_text) or None, "tool_calls": [tc.to_message() for tc in tool_calls]})
            for tc in tool_calls:
                args = tc.parsed_arguments()
                label = status_label(tc.name, args, locale, persona.id)
                last_status = label
                yield ev.status("tool", label)
                key = _args_key(tc.name, args)
                if key in cache:
                    result = cache[key]
                else:
                    result = await execute_tool(tc.name, args, ctx)
                    cache[key] = result
                    results.append((tc.name, result))
                    for widget in result.widgets:
                        yield ev.widget_event(widget)
                yield ev.tool_event(tc.name, args, result.summary)
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result.llm_payload, ensure_ascii=False, default=str)})
    except LLMUnavailable as exc:
        log.warning("LLM unavailable, switching to offline answer: %s", exc)
        if not results and not answer_parts:
            from app.agent.fallback import run_fallback

            if trace is not None:
                trace["mode"] = "offline"
            async for event in run_fallback(req, ctx, message_id=message_id, announce=False, trace=trace):
                yield event
            return
    except LLMStreamInterrupted as exc:
        log.warning("LLM stream interrupted: %s", exc)
        if "".join(answer_parts).strip():
            # Half an answer is on the screen: say so instead of ending as if it were whole.
            truncated = True
            tail = f" …\n\n{INTERRUPTED_TEXT[locale]}"
            yield ev.token(tail)
            answer_parts.append(tail)
        elif not results:
            # Nothing visible yet and no data fetched: let the offline coach answer.
            from app.agent.fallback import run_fallback

            if trace is not None:
                trace["mode"] = "offline"
            async for event in run_fallback(req, ctx, message_id=message_id, announce=False, trace=trace):
                yield event
            return
    except Exception:  # noqa: BLE001 - never break the SSE stream
        log.exception("Chat orchestration failed")
        if not answer_parts and not results:
            yield ev.error(ERROR_TEXT[locale])
            return

    if not "".join(answer_parts).strip():
        # Model produced no visible text (or failed after tools): compose it ourselves.
        from app.agent.fallback import compose_answer, stream_text

        text = compose_answer(results, persona, locale, user_text=req.last_user_text, recovery_context=user_ctx.numbers.get("recovery"))
        yield ev.status("writing", persona.text("status.writing", locale, WRITING_LABEL[locale]))
        async for event in stream_text(text):
            yield event
        answer_parts.append(text)
        composed = True
    else:
        composed = False

    guardrail: str | None = None
    if not composed and not truncated:  # our own templates need no review
        try:
            guardrail, correction = guardrails.review(
                "".join(answer_parts),
                tools_ran=bool(results),
                shown=[user_ctx.render()],
                conversation="\n".join(m.content for m in req.messages),
                locale=locale,
            )
        except Exception:  # noqa: BLE001 - a broken check must never break the answer
            log.exception("Answer review failed")
            guardrail, correction = None, ""
        if guardrail:
            log.warning("Answer guardrail %s triggered for %s", guardrail, message_id)
            yield ev.token(f"\n\n{correction}")
    if trace is not None:
        trace["guardrail"] = guardrail
        trace["truncated"] = truncated

    tools_used = [name for name, _ in results]
    yield ev.done(
        message_id,
        merge_sources(results, locale),
        suggest_followups(tools_used, persona.id, locale, req.last_user_text, results, recovery_context=user_ctx.numbers.get("recovery")),
        derive_mood(results, recovery_context=user_ctx.numbers.get("recovery")),
        truncated=truncated,
        guardrail=guardrail,
    )


async def collect(req: ChatRequest, **kwargs: Any) -> list[SSEEvent]:
    """Run a chat turn to completion and return all events (evals, tests, scripts)."""
    return [e async for e in run_chat(req, **kwargs)]
