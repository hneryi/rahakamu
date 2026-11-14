"""Shared FastAPI dependencies and request models for the REST layer.

Routers are deliberately *thin*: validate input with Pydantic, call one analytics
function, return its JSON. All business logic lives in :mod:`app.analytics`, so the
agent's tools and the REST API can never drift apart.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import Path
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import db

CustomerId = Annotated[str, Path(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_-]+$",
                                 description="Dataset customer id, e.g. CUST05020")]


def require_customer(customer_id: str) -> str:
    """Raise :class:`app.db.CustomerNotFound` (→ 404) for unknown ids."""
    db.ensure_customer(customer_id)
    return customer_id


class Adjustment(BaseModel):
    """One what-if change: target exactly what you want to change by ``change_pct``."""

    model_config = ConfigDict(extra="forbid")
    category: str | None = Field(default=None, examples=["Restaurants"])
    basket: Literal["fixed", "irregular", "leak"] | None = None
    merchant: str | None = Field(default=None, examples=["MRC-RES-0038"])
    mcc: int | None = Field(default=None, examples=[4121])
    change_pct: float = Field(ge=-100, le=200, examples=[-20])

    @model_validator(mode="after")
    def _one_target(self) -> Adjustment:
        if not any([self.category, self.basket, self.merchant, self.mcc is not None]):
            raise ValueError("adjustment needs category, basket, merchant or mcc")
        return self


class WhatIfRequest(BaseModel):
    adjustments: list[Adjustment] = Field(min_length=1, max_length=10)
    horizon_months: int = Field(default=12, ge=1, le=120)
    invest_return_pct: float = Field(default=0.0, ge=-20, le=20)


GoalKind = Literal["car", "travel", "home", "emergency", "education", "gadget", "other"]


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80, examples=["Car"])
    target_amount: float = Field(gt=0, le=10_000_000, examples=[12000])
    deadline: str | None = Field(default=None, examples=["2027-09-30"])
    emoji: str | None = Field(default=None, max_length=8)
    kind: GoalKind = "other"
    saved_amount: float = Field(default=0.0, ge=0, le=10_000_000)


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    target_amount: float | None = Field(default=None, gt=0, le=10_000_000)
    deadline: str | None = None
    emoji: str | None = Field(default=None, max_length=8)
    kind: GoalKind | None = None
    saved_amount: float | None = Field(default=None, ge=0, le=10_000_000)
    monthly_contribution: float | None = Field(default=None, ge=0, le=1_000_000)
    add_amount: float | None = Field(default=None, ge=-10_000_000, le=10_000_000,
                                     description="Deposit towards the goal (adds to saved_amount)")

    def fields(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class GoalPlanRequest(BaseModel):
    target_amount: float = Field(gt=0, le=10_000_000, examples=[12000])
    deadline: str | None = Field(default=None, examples=["2027-09-30"])
    name: str | None = Field(default=None, max_length=80, examples=["Car"])
    saved_amount: float = Field(default=0.0, ge=0, le=10_000_000)
