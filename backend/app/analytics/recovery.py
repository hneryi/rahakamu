"""Recovery state: is the customer merely tight, or actually in the red?

Why
---
A generic nudge ("you can spend 12 € a day") is misleading when the account is
negative or when income has been below spending for months. The coach has to say which
of three situations the customer is in, so the advice is honest:

* ``balance_repair`` — the account balance is below zero (money is already gone).
* ``cashflow_stabilizing`` — balance is fine, but the six complete months show spending
  above income, so the buffer is shrinking.
* ``ordinary`` — balance and cashflow are both at or above zero.
* ``unknown`` — the data is missing or not finite; never pretend it is green.

``urgency`` (safe-to-spend ``critical``/``tight``/``comfortable``) is a *separate*
indicator: it says how much can be spent before payday, not whether the customer is
insolvent. It also reserves planned goal contributions, so tightness caused by goals
must not be reported as "food or bills no longer fit".

Everything here is deterministic, cent-accurate and cheap: the six-month averages come
from ``monthly_flows`` (saving transfers are not spending), the balance from
``current_balance`` and the availability check from a bounded transaction count. No
hysteresis and no lifecycle: a payday balance is a snapshot, not a permanent recovery.
"""

from __future__ import annotations

import math
from typing import Any

from app import db
from app.analytics.common import (
    current_balance,
    full_months_window,
    monthly_flows,
    r2,
    tx_count_and_period,
)
from app.analytics.safe_to_spend import safe_to_spend

STATE_BALANCE_REPAIR = "balance_repair"
STATE_CASHFLOW_STABILIZING = "cashflow_stabilizing"
STATE_ORDINARY = "ordinary"
STATE_UNKNOWN = "unknown"
STATES = (STATE_BALANCE_REPAIR, STATE_CASHFLOW_STABILIZING, STATE_ORDINARY, STATE_UNKNOWN)
MONTHS = 6


def _cents(value: Any) -> int | None:
    """Money as integer cents; ``None``/NaN/inf are "not known"."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return int(round(f * 100))


def classify(balance: Any, surplus: Any) -> str:
    """Pure classifier: negative balance wins, then a negative six-month surplus.

    ``balance_repair`` when the balance is below zero, ``cashflow_stabilizing`` when the
    balance is at or above zero but spending exceeds income, ``ordinary`` when both are
    at or above zero, ``unknown`` when either value is missing or not finite.
    """
    balance_cents, surplus_cents = _cents(balance), _cents(surplus)
    if balance_cents is None or surplus_cents is None:
        return STATE_UNKNOWN
    if balance_cents < 0:
        return STATE_BALANCE_REPAIR
    if surplus_cents < 0:
        return STATE_CASHFLOW_STABILIZING
    return STATE_ORDINARY


def recovery(customer_id: str, sts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shared recovery snapshot for nudges, overview, tools and the offline agent.

    ``planned_monthly_change`` is the honest monthly correction: the average deficit plus
    the monthly contributions the active goals already plan, and only when a deficit
    exists. Goal progress does not change the account balance, so ``saved_amount`` never
    moves this state.
    """
    from app.analytics.goals import list_goals

    db.ensure_customer(customer_id)
    flows = monthly_flows(customer_id, MONTHS)
    balance = current_balance(customer_id)
    start, end = full_months_window(MONTHS)
    counted = tx_count_and_period(customer_id, start, end)
    known = counted["tx_count"] > 0
    state = classify(balance if known else None, flows["surplus"] if known else None)

    active = [g for g in list_goals(customer_id) if g["progress"] < 1]
    goal_need = r2(sum(float(g["monthly_contribution"] or 0.0) for g in active))
    deficit = r2(max(0.0, -flows["surplus"])) if state != STATE_UNKNOWN else 0.0
    planned = r2(deficit + goal_need) if deficit > 0 else None

    sts = sts if sts is not None else safe_to_spend(customer_id)
    urgency = sts["status"]
    goal_contributions = r2(sts["goal_contributions"])

    snapshot = {
        "state": state,
        "months": MONTHS,
        "balance": balance,
        "monthly_income": flows["income"],
        "monthly_spending": flows["spending"],
        "monthly_surplus": flows["surplus"],
        "deficit": deficit,
        "goal_monthly_need": goal_need,
        "planned_monthly_change": planned,
        "urgency": urgency,
        "safe_per_day": sts["safe_per_day"],
        "days_until_payday": sts["days_until_payday"],
        "goal_contributions": goal_contributions,
        "goal_reservations_present": goal_contributions > 0,
        "tx_count": counted["tx_count"],
        "period": counted["period"],
    }
    # JSON has no NaN/Infinity; unknown must not look like a zero or a green light.
    for key, value in snapshot.items():
        if isinstance(value, float) and not math.isfinite(value):
            snapshot[key] = None
    if state == STATE_UNKNOWN:
        snapshot.update(urgency=None, safe_per_day=None, deficit=None)
    return snapshot
