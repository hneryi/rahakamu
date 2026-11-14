"""SPankkiBot API — FastAPI application entry point.

Run locally::

    cd backend && uv run uvicorn app.main:app --reload --port 8000

Open http://localhost:8000/docs for the interactive OpenAPI documentation.

Design
------
* Every route lives under ``/api`` (SPEC §3.2) so the API can sit behind the same origin as
  the web build or behind an S-mobiili API gateway without rewriting paths.
* CORS: production serves the web app and the API from one origin, which needs no CORS, so
  only localhost / private-network development origins are allowed by default. Add other
  origins with ``CORS_ORIGINS``.
* Public-demo limits (request size, chat rate limits, LLM concurrency) live in
  :mod:`app.limits`.
* Domain errors map to HTTP: unknown customer / goal → 404, invalid input → 422. Anything
  unexpected becomes a plain ``500 {"detail": …}``: no stack trace ever reaches a client.
* The chat router (SSE agent) is owned by the agent module and included *defensively*: the
  analytics API keeps working even if the agent cannot be imported.
* On startup the DuckDB cache is warmed in the background so the first request is fast.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import db
from app.analytics.goals import GoalNotFound
from app.config import settings
from app.i18n import LocaleMiddleware, tr, use_locale
from app.limits import BodyLimitMiddleware, message
from app.routers import customers, meta

log = logging.getLogger("spankkibot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db.start_warmup()  # background thread; /api/health reports "starting" until it is done
    yield


app = FastAPI(
    title="Rahakamu API",
    version="1.0.0",
    description=("Personal Economic Trainer for S-Bank customers: analytics over the customer's own "
                 "transactions (three baskets, safe-to-spend, goals, benchmarks…) and an AI coach chat."),
    lifespan=lifespan,
)
# Middleware runs outside-in in reverse order of registration: CORS → locale → body limit.
app.add_middleware(BodyLimitMiddleware)  # 413 above MAX_BODY_BYTES, before anything is parsed
app.add_middleware(LocaleMiddleware)  # ?locale=en|fi|sv → texts and labels (SPEC §5.6)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Accept", "Accept-Language", "Cache-Control", "Last-Event-ID", "X-Requested-With"],
    max_age=600,
)


@app.exception_handler(db.CustomerNotFound)
async def _customer_404(_: Request, exc: db.CustomerNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": tr(f"Unknown customer {exc.args[0]!s}",
                                                               f"Tuntematon asiakas {exc.args[0]!s}",
                                                               f"Okänd kund {exc.args[0]!s}")})


@app.exception_handler(GoalNotFound)
async def _goal_404(_: Request, exc: GoalNotFound) -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": tr(f"Unknown goal {exc.args[0]!s}",
                                                               f"Tuntematon tavoite {exc.args[0]!s}",
                                                               f"Okänt mål {exc.args[0]!s}")})


@app.exception_handler(ValueError)
async def _value_422(_: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(OverflowError)
async def _overflow_422(_: Request, __: OverflowError) -> JSONResponse:
    """A number or date so large that the maths overflowed: the caller's input, not a bug."""
    return JSONResponse(status_code=422, content={"detail": message("out_of_range")})


@app.exception_handler(Exception)
async def _unexpected_500(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: log the details server-side, tell the client nothing about internals.

    This handler runs outside the locale middleware, so the locale is read from the query.
    """
    log.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path)
    with use_locale(request.query_params.get("locale")):
        return JSONResponse(status_code=500, content={"detail": message("server_error")})


app.include_router(meta.router, prefix="/api")
app.include_router(customers.router, prefix="/api")

try:  # the agent builder owns app/routers/chat.py; never let it take the analytics API down
    from app.routers import chat as _chat

    if hasattr(_chat, "router"):
        app.include_router(_chat.router, prefix="/api")
except Exception:  # noqa: BLE001
    log.warning("Chat router not available; /api/chat disabled", exc_info=True)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {"name": "Rahakamu API", "docs": "/docs", "health": "/api/health"}
