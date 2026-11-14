"""Abuse controls for a public demo: rate limits, an LLM concurrency cap and size limits.

Why this module exists
----------------------
The demo API has no login, so anyone who finds the URL can call it. Three things must not
be possible: draining the LLM budget, exhausting the server's memory, and making the
service unusable for the people at the demo. This module holds the small, dependency-free
building blocks the routers use for that:

* :class:`SlidingWindowLimiter`: in-process requests-per-minute limits per client IP and
  per customer. **Per worker**: with ``uvicorn --workers 2`` the effective limit is up to
  twice the configured number, which is fine for a demo (a shared store such as Redis is
  the production answer).
* :func:`llm_semaphore`: at most ``CHAT_MAX_CONCURRENT_LLM`` chat turns talk to the LLM at
  once (per worker). A turn that cannot get a slot within ``CHAT_QUEUE_WAIT_S`` is answered
  by the offline rule-based coach instead of queueing, so the user still gets an answer.
* :func:`check_chat_request`: message, history and image size limits with messages in the
  user's language.
* :class:`BodyLimitMiddleware`: rejects request bodies above ``MAX_BODY_BYTES`` with 413,
  before they are buffered and parsed.
* :func:`client_ip`: the caller's address. ``X-Forwarded-For`` is trusted only when the
  direct peer is the local reverse proxy (Caddy on 127.0.0.1), and then only its last
  entry, which is the one the proxy itself appended.

Every limit is configurable by environment variable (see ``app.config.Settings``);
``0`` switches a limit off.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import math
import threading
import time
import weakref
from collections import deque
from typing import Any

from starlette.exceptions import HTTPException

from app.config import settings
from app.i18n import tr

LOOPBACK = {"127.0.0.1", "::1", "localhost"}


# ------------------------------------------------------------------------------ texts
def message(code: str) -> str:
    """User-facing text for a limit, in the current locale (see :mod:`app.i18n`)."""
    if code == "rate_limited":
        return tr("You are sending messages very quickly. Please wait a moment and try again.",
                  "Lähetät viestejä todella nopeasti. Odota hetki ja yritä uudelleen.",
                  "Du skickar meddelanden väldigt snabbt. Vänta en stund och försök igen.")
    if code == "message_too_long":
        n = settings.chat_max_message_chars
        return tr(f"That message is too long (max {n} characters). Please shorten it.",
                  f"Viesti on liian pitkä (enintään {n} merkkiä). Lyhennä sitä.",
                  f"Meddelandet är för långt (högst {n} tecken). Korta ner det.")
    if code == "history_too_long":
        return tr("This conversation has become too long. Please start a new chat.",
                  "Keskustelu on kasvanut liian pitkäksi. Aloita uusi keskustelu.",
                  "Den här konversationen har blivit för lång. Starta en ny chatt.")
    if code == "image_too_large":
        mb = f"{settings.chat_max_image_bytes / 1_000_000:g}"
        mb_comma = mb.replace(".", ",")  # decimal comma in Finnish and Swedish
        return tr(f"That photo is too large (max {mb} MB). Please send a smaller one.",
                  f"Kuva on liian suuri (enintään {mb_comma} Mt). Lähetä pienempi kuva.",
                  f"Bilden är för stor (högst {mb_comma} MB). Skicka en mindre bild.")
    if code == "image_invalid":
        return tr("I could not read that photo. Please send a JPEG or PNG image.",
                  "En pystynyt lukemaan kuvaa. Lähetä JPEG- tai PNG-kuva.",
                  "Jag kunde inte läsa bilden. Skicka en JPEG- eller PNG-bild.")
    if code == "body_too_large":
        return tr("The request is too large.", "Pyyntö on liian suuri.", "Förfrågan är för stor.")
    if code == "server_error":
        return tr("Something went wrong on our side. Please try again.",
                  "Jokin meni pieleen meidän päässämme. Yritä uudelleen.",
                  "Något gick fel hos oss. Försök igen.")
    if code == "out_of_range":
        return tr("A value in the request is out of range.",
                  "Jokin pyynnön arvo on sallitun alueen ulkopuolella.",
                  "Ett värde i förfrågan ligger utanför det tillåtna intervallet.")
    raise KeyError(code)


# ------------------------------------------------------------------------- rate limits
class SlidingWindowLimiter:
    """Requests per ``window_s`` per key, kept in memory (one instance per worker)."""

    def __init__(self, window_s: float = 60.0, max_keys: int = 20_000) -> None:
        self.window_s = window_s
        self.max_keys = max_keys
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int) -> float:
        """Record one request. Returns 0.0 if allowed, else the seconds until a slot frees.

        Rejected requests are not recorded, so a blocked client recovers as soon as its
        oldest request leaves the window. ``limit <= 0`` disables the check.
        """
        if limit <= 0:
            return 0.0
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                if len(self._hits) >= self.max_keys:
                    self._prune(now)
                q = self._hits[key] = deque()
            while q and now - q[0] >= self.window_s:
                q.popleft()
            if len(q) >= limit:
                return max(0.05, self.window_s - (now - q[0]))
            q.append(now)
            return 0.0

    def _prune(self, now: float) -> None:
        stale = [k for k, q in self._hits.items() if not q or now - q[-1] >= self.window_s]
        for k in stale:
            del self._hits[k]
        if len(self._hits) >= self.max_keys:  # under a flood of distinct keys: start over
            self._hits.clear()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


chat_ip_limiter = SlidingWindowLimiter()
chat_customer_limiter = SlidingWindowLimiter()
feedback_ip_limiter = SlidingWindowLimiter()


def reset_limiters() -> None:
    """Forget all counters (tests)."""
    for limiter in (chat_ip_limiter, chat_customer_limiter, feedback_ip_limiter):
        limiter.reset()


def too_many(limiter: SlidingWindowLimiter, key: str, limit: int) -> HTTPException | None:
    """``None`` if the request may proceed, else a ready 429 with ``Retry-After``."""
    wait = limiter.hit(key, limit)
    if wait <= 0:
        return None
    return HTTPException(status_code=429, detail=message("rate_limited"),
                         headers={"Retry-After": str(max(1, math.ceil(wait)))})


def client_ip(request: Any) -> str:
    """Address of the caller. ``X-Forwarded-For`` counts only when the peer is loopback."""
    peer = request.client.host if getattr(request, "client", None) else ""
    if peer in LOOPBACK or not peer:
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.split(",")[-1].strip()
        if last:
            return last[:64]
    return peer or "unknown"


# ---------------------------------------------------------------------- LLM concurrency
_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, tuple[int, asyncio.Semaphore]] = weakref.WeakKeyDictionary()


def llm_semaphore() -> asyncio.Semaphore | None:
    """The running loop's LLM slot counter, or ``None`` when the cap is switched off."""
    size = int(settings.chat_max_concurrent_llm)
    if size <= 0:
        return None
    loop = asyncio.get_running_loop()
    held = _semaphores.get(loop)
    if held is None or held[0] != size:
        held = (size, asyncio.Semaphore(size))
        _semaphores[loop] = held
    return held[1]


async def acquire_llm_slot() -> tuple[bool, asyncio.Semaphore | None]:
    """Try to take an LLM slot. ``(True, sem)`` → release ``sem`` when the turn ends;
    ``(True, None)`` → no cap; ``(False, None)`` → busy, answer offline instead."""
    sem = llm_semaphore()
    if sem is None:
        return True, None
    if not sem.locked():
        await sem.acquire()  # a slot is free: this returns at once
        return True, sem
    wait = float(settings.chat_queue_wait_s)
    if wait <= 0:
        return False, None
    try:
        await asyncio.wait_for(sem.acquire(), timeout=wait)
    except (TimeoutError, asyncio.TimeoutError):
        return False, None
    return True, sem


# -------------------------------------------------------------------- chat input limits
_IMAGE_MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")


def clean_image_base64(data: str) -> str:
    """Raw base64 without a ``data:`` prefix or whitespace."""
    data = data.strip()
    if data.startswith("data:"):
        data = data.split(",", 1)[1] if "," in data else ""
    return "".join(data.split())


def check_image(data: str) -> str | None:
    """``None`` if ``data`` is an acceptable JPEG / PNG / WebP, else an error code."""
    raw = clean_image_base64(data)
    if not raw:
        return "image_invalid"
    if len(raw) * 3 // 4 > settings.chat_max_image_bytes > 0:
        return "image_too_large"
    try:
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=True)
    except (binascii.Error, ValueError):
        return "image_invalid"
    is_webp = decoded[:4] == b"RIFF" and decoded[8:12] == b"WEBP"
    if not (decoded.startswith(_IMAGE_MAGIC) or is_webp):
        return "image_invalid"
    return None


def check_chat_request(req: Any) -> str | None:
    """Size limits for one chat turn. Returns an error code for :func:`message` or ``None``."""
    if 0 < settings.chat_max_history_messages < len(req.messages):
        return "history_too_long"
    if 0 < settings.chat_max_message_chars < len(req.last_user_text):
        return "message_too_long"
    if req.image_base64:
        return check_image(req.image_base64)
    return None


# -------------------------------------------------------------------------- body limit
class BodyTooLarge(HTTPException):
    """413 raised while the body is being read (FastAPI passes HTTPExceptions through)."""

    def __init__(self) -> None:
        super().__init__(status_code=413, detail=message("body_too_large"))


class BodyLimitMiddleware:
    """Pure ASGI middleware: refuse bodies above ``MAX_BODY_BYTES``.

    A declared ``Content-Length`` above the limit is refused before a single body byte is
    read. Chunked uploads are counted as they arrive and cut off at the limit, so a client
    can never make the server buffer more than the limit.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        limit = int(settings.max_body_bytes)
        if scope.get("type") != "http" or limit <= 0 or scope.get("method") in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        declared = dict(scope.get("headers") or []).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await self._reject(send)
            return
        received = 0

        async def limited_receive() -> dict[str, Any]:
            nonlocal received
            msg = await receive()
            if msg.get("type") == "http.request":
                received += len(msg.get("body") or b"")
                if received > limit:
                    raise BodyTooLarge()
            return msg

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(send: Any) -> None:
        body = json.dumps({"detail": message("body_too_large")}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 413,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()),
                                (b"connection", b"close")]})
        await send({"type": "http.response.body", "body": body})
