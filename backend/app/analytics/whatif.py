"""What-if simulator: "How much could I save if I reduced dining out by 20 %?"

Why
---
Seeing *your own* number ("−20 % eating out = 49 €/month = 590 € a year, 612 € if
invested at 3 %") is far more motivating than generic advice, and the slider in the app
calls this endpoint live so users can *play* with their budget (learning by doing).

Method
------
* Baseline = average monthly spending of the matched transactions over the last 6
  complete months (spending baskets only).
* An adjustment targets ``{"category": ...}``, ``{"basket": ...}``, ``{"merchant": ...}``
  or ``{"mcc": ...}`` with ``change_pct`` (−100 … +200). Each spending group is matched by
  the **first** adjustment that applies, so overlapping adjustments never double count.
* ``with_return`` compounds the monthly saving at ``invest_return_pct`` (annual, monthly
  compounding) — a teaching device about the time value of money, not investment advice.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.analytics.common import full_months_window, r2, basket_label
from app.analytics.labels import category_label_l10n, merchant_label
from app.i18n import tr
from app.analytics.query import _norm_basket, _norm_category

WINDOW_MONTHS = 6


def _matches(adj: dict[str, Any], row: dict[str, Any]) -> bool:
    if adj.get("category") and row["category"] != adj["category"]:
        return False
    if adj.get("basket") and row["basket"] != adj["basket"]:
        return False
    if adj.get("merchant") and (row["merchant_id"] or "").upper() != str(adj["merchant"]).upper():
        return False
    return not (adj.get("mcc") is not None and row["mcc_code"] != int(adj["mcc"]))


def _label(adj: dict[str, Any]) -> str:
    if adj.get("merchant"):
        return merchant_label(adj["merchant"], adj.get("mcc"), adj.get("category"))
    parts = []
    if adj.get("category"):
        parts.append(category_label_l10n(adj["category"]) or adj["category"])
    if adj.get("basket"):
        parts.append(basket_label(adj["basket"]))
    if adj.get("mcc") is not None:
        parts.append(f"MCC {adj['mcc']}")
    return " · ".join(parts) or tr("All spending", "Kaikki kulutus", "All konsumtion")


def simulate_what_if(customer_id: str, adjustments: list[dict[str, Any]], horizon_months: int = 12,
                     invest_return_pct: float = 0.0) -> dict[str, Any]:
    """Project the effect of spending changes (see module docstring)."""
    db.ensure_customer(customer_id)
    horizon = max(1, min(int(horizon_months), 120))
    ret = float(invest_return_pct or 0.0)
    if not -20 <= ret <= 20:
        raise ValueError("invest_return_pct must be between -20 and 20")
    if not adjustments:
        raise ValueError("At least one adjustment is required")
    adjs: list[dict[str, Any]] = []
    for a in adjustments:
        a = dict(a)
        pct = float(a.get("change_pct", 0))
        if not -100 <= pct <= 200:
            raise ValueError("change_pct must be between -100 and 200")
        cats = _norm_category(a.get("category")) if a.get("category") else None
        norm = {
            "category": cats[0] if cats else None,
            "basket": _norm_basket(a.get("basket")),
            "merchant": a.get("merchant") or None,
            "mcc": int(a["mcc"]) if a.get("mcc") not in (None, "") else None,
            "change_pct": pct,
        }
        if not any(norm[k] is not None for k in ("category", "basket", "merchant", "mcc")):
            raise ValueError("Each adjustment needs a category, basket, merchant or mcc")
        adjs.append(norm)

    start, end = full_months_window(WINDOW_MONTHS)
    rows = db.query(
        "SELECT category, basket, merchant_id, mcc_code, sum(-tx_amount_eur) AS total, count(*) AS n "
        "FROM tx WHERE customer_id = ? AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 "
        "AND basket IN ('fixed','irregular','leak') GROUP BY ALL",
        [customer_id, start, end],
    )
    per = [{"baseline": 0.0, "count": 0} for _ in adjs]
    total_spend = 0.0
    for r in rows:
        monthly = float(r["total"]) / WINDOW_MONTHS
        total_spend += monthly
        for i, a in enumerate(adjs):
            if _matches(a, r):
                per[i]["baseline"] += monthly
                per[i]["count"] += int(r["n"])
                break

    per_item = []
    baseline = new = 0.0
    for a, p in zip(adjs, per, strict=True):
        b = p["baseline"]
        n = b * (1 + a["change_pct"] / 100)
        baseline += b
        new += n
        per_item.append({
            "label": _label(a),
            "category": a["category"], "basket": a["basket"], "merchant": a["merchant"], "mcc": a["mcc"],
            "change_pct": a["change_pct"],
            "baseline_monthly": r2(b),
            "new_monthly": r2(n),
            "monthly_saving": r2(b - n),
            "yearly_saving": r2((b - n) * 12),
            "tx_count": p["count"],
        })
    monthly_saving = baseline - new
    i = (1 + ret / 100) ** (1 / 12) - 1
    series, cum = [], 0.0
    for m in range(1, horizon + 1):
        cum = cum * (1 + i) + monthly_saving
        series.append({"month": m, "cumulative": r2(cum),
                       "cumulative_no_return": r2(monthly_saving * m)})
    return {
        "baseline_monthly": r2(baseline),
        "new_monthly": r2(new),
        "monthly_saving": r2(monthly_saving),
        "horizon_months": horizon,
        "total_saving": r2(monthly_saving * horizon),
        "with_return": r2(cum),
        "invest_return_pct": ret,
        "per_item": per_item,
        "series": series,
        "share_of_spending": round(baseline / total_spend, 4) if total_spend else 0.0,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "months": WINDOW_MONTHS},
    }
