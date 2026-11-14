"""Non-customer endpoints: health, learning content, personas, basket rules."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app import content
from app.analytics.baskets import explanations, rules
from app.config import settings
from app.i18n import norm_locale, use_locale

#: ``en`` / ``fi`` / ``sv``; anything else (``de``, ``sv-FI``…) is normalised, never a 422.
LocaleParam = Annotated[str, Query(description="en | fi | sv (unknown values fall back to en)")]

router = APIRouter(tags=["meta"])


def _data_state() -> str:
    """``ready`` | ``loading`` | ``error``, without ever waiting for the cache build."""
    try:
        from app import db

        if not db.is_ready():
            db.start_warmup()  # idempotent; also retries a failed build
        return db.readiness()
    except Exception:  # noqa: BLE001 - health must never raise
        return "error"


def _llm_available() -> bool:
    """True when this worker has a configured provider that is not in a cool-down."""
    try:
        from app.agent.llm import get_llm
        from app.agent.orchestrator import offline_forced

        client = get_llm()
        return client.configured and client.any_healthy() and not offline_forced()
    except Exception:  # noqa: BLE001 - health must never raise
        return False


@router.get("/health", summary="Liveness + readiness + configuration flags (never exposes secrets)")
async def health() -> dict[str, Any]:
    """Answers immediately, also while the DuckDB cache is still being built on first boot.

    ``async`` on purpose: it runs on the event loop and needs no worker thread, so it also
    answers while every worker thread is busy waiting for the first cache build.

    ``status`` is ``ok`` (data loaded), ``starting`` (cache loading or building) or
    ``degraded`` (the last load failed; it is retried in the background). ``llm.primary`` /
    ``llm.fallback`` say what is *configured*; ``llm.available`` says whether this worker
    can reach a model right now (false while every provider is in a cool-down, when the
    chat answers with the offline coach).
    """
    state = _data_state()
    return {
        "status": {"ready": "ok", "loading": "starting"}.get(state, "degraded"),
        "ready": state == "ready",
        "as_of": settings.as_of_date.isoformat(),
        "llm": {"primary": settings.llm_configured,
                "fallback": bool(settings.llm_fallback_base_url and settings.llm_fallback_model),
                "available": _llm_available()},
        "data": {"loaded": state == "ready", "state": state},
    }


@router.get("/ready", summary="Readiness probe: 200 once the ledger data is loaded, else 503")
async def ready() -> JSONResponse:
    state = _data_state()
    return JSONResponse(status_code=200 if state == "ready" else 503,
                        content={"ready": state == "ready", "data": {"state": state}})


@router.get("/lessons", summary="Money Gym lessons, localised")
def lessons(
    locale: LocaleParam = "en",
    customer_id: str | None = Query(None, description="Evaluate unlock rules for this customer"),
) -> dict[str, Any]:
    return content.get_lessons(norm_locale(locale), customer_id)


@router.get("/personas", summary="AI coach personas (Sisu & Aava)")
def personas(locale: LocaleParam | None = None) -> Any:
    return content.get_personas(norm_locale(locale) if locale else None)


@router.get("/baskets/rules", summary="How transactions are sorted into the three baskets")
def basket_rules(locale: LocaleParam = "en") -> dict[str, Any]:
    with use_locale(locale):
        return {"explanations": explanations(), "rules": rules()}
