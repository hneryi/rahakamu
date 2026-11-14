"""Home readiness: "Could I get a mortgage, and if not, what is missing?"

Why
---
Buying a first home is the biggest financial decision most customers make, and rejection
is demoralising when nobody explains *why*. We learn the bank's own decision patterns from
the challenge's mortgage dataset (200 applications, 150 approved) and hold them against
the customer's real income and savings, turning a yes/no into a to-do list.

Ratios learned from the dataset (computed live, so they update with new data)
------------------------------------------------------------------------------
* **Required monthly income ≈ k × loan** — a near-perfect linear rule in the data
  (k ≈ 1.84 % of the loan per month, R² ≈ 1).
* **Typical loan-to-value** = median LTV of approved applications (≈ 85 %), so the
  equity needed ≈ 15 % of the price.
* **Closing costs** = median transfer-tax ratio from the negotiation history (≈ 2.6 %).
* Rejection reasons (insufficient collateral / equity / income, existing debt) become the
  vocabulary of the ``gaps`` list.

The customer's side: average monthly income (last 6 complete months) and an *equity
estimate* = current balance + what was moved to savings/investments during the last 12
months (deposits + sweeps − withdrawals), assuming that money is still there. Twelve months
keeps the estimate conservative: older transfers may already have been spent elsewhere.

Also shown: an annuity payment estimate (25 years at 4 %) and the Finnish FIN-FSA style
stress test at 6 %, because "can I afford it if rates rise?" is the real question.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.analytics.common import add_months, as_of, current_balance, monthly_flows, r2
from app.i18n import eur, loc, tr

LOAN_YEARS = 25
RATE_PCT = 4.0
STRESS_RATE_PCT = 6.0

REJECTION_LESSONS: dict[str, str] = {
    "insufficient_collateral": ("The property's valued collateral did not cover the loan well enough. "
                                "Options: a bigger down payment, additional collateral (e.g. a family "
                                "guarantee) or a state guarantee for first-home buyers."),
    "insufficient_equity": "The down payment was too small. Building savings is the most direct fix.",
    "insufficient_income": "Income was too low for the loan size. A cheaper home or a co-applicant helps.",
    "existing_debt": "Existing debts took up too much repayment capacity. Paying them down comes first.",
}


REJECTION_LESSONS_L10N: dict[str, dict[str, str]] = {
    "fi": {
        "insufficient_collateral": ("Asunnon arvioitu vakuusarvo ei kattanut lainaa riittävästi. Vaihtoehdot: "
                                    "suurempi käsiraha, lisävakuus (esim. perheen takaus) tai valtion takaus "
                                    "ensiasunnon ostajalle."),
        "insufficient_equity": "Käsiraha oli liian pieni. Säästöjen kasvattaminen on suorin korjaus.",
        "insufficient_income": "Tulot olivat liian pienet lainan kokoon nähden. Edullisempi koti tai kanssahakija auttaa.",
        "existing_debt": "Nykyiset velat veivät liikaa maksukykyä. Niiden lyhentäminen tulee ensin.",
        "approved": "Hyväksytty: suunnitelma täytti pankin kriteerit.",
    },
    "sv": {
        "insufficient_collateral": ("Bostadens värderade säkerhet täckte inte lånet tillräckligt. Alternativ: "
                                    "en större egen insats, ytterligare säkerhet (t.ex. borgen från familjen) "
                                    "eller statsborgen för förstagångsköpare."),
        "insufficient_equity": "Den egna insatsen var för liten. Att bygga upp sparandet är den mest direkta lösningen.",
        "insufficient_income": "Inkomsten var för låg för lånets storlek. En billigare bostad eller en medsökande hjälper.",
        "existing_debt": "Befintliga skulder tog för stor del av betalningsförmågan. Att betala av dem kommer först.",
        "approved": "Beviljat: planen uppfyllde bankens kriterier.",
    },
}


def _lesson(reason: str | None) -> str:
    current = loc()
    if current == "en":
        return REJECTION_LESSONS.get(reason or "", "Approved: the plan fit the bank's criteria.")
    table = REJECTION_LESSONS_L10N[current]
    return table.get(reason or "", table["approved"])


def _n(value: float) -> str:
    """Whole euros without the sign: ``30,717`` (en) / ``30 717`` (fi, sv)."""
    return eur(value, 0)[:-2]


@lru_cache(maxsize=1)
def dataset_ratios() -> dict[str, Any]:
    """Decision ratios learned from the mortgage dataset (cached per process)."""
    r = db.query_one(
        "SELECT count(*) AS n, count(*) FILTER (WHERE final_decision = 'approved') AS approved,"
        " regr_slope(required_monthly_income_eur, final_requested_loan_eur) AS k,"
        " regr_r2(required_monthly_income_eur, final_requested_loan_eur) AS r2,"
        " median(lfinal_loan_to_value) FILTER (WHERE final_decision = 'approved') AS ltv,"
        " median(final_property_price_eur) FILTER (WHERE final_decision = 'approved') AS price,"
        " median(final_collateral_value_eur / final_requested_loan_eur)"
        "   FILTER (WHERE final_decision = 'approved') AS collateral_ratio"
        " FROM mortgages"
    ) or {}
    reasons = db.query("SELECT rejection_reason AS reason, count(*) AS n FROM mortgages "
                       "WHERE final_decision = 'rejected' GROUP BY 1 ORDER BY 2 DESC")
    tax = db.scalar(
        "SELECT median(TRY_CAST(expense_amount AS DOUBLE) / TRY_CAST(property_price_estimate AS DOUBLE)) "
        "FROM mortgage_events WHERE event_type = 'expense_recorded' AND expense_type = 'transfer_tax'"
    )
    n = int(r.get("n") or 0)
    return {
        "applications": n,
        "approved": int(r.get("approved") or 0),
        "approval_rate": round((r.get("approved") or 0) / n, 3) if n else None,
        "income_per_loan_euro": float(r["k"]) if r.get("k") else 0.0184,
        "income_fit_r2": round(float(r["r2"]), 4) if r.get("r2") else None,
        "typical_ltv": float(r["ltv"]) if r.get("ltv") else 0.85,
        "median_price": float(r["price"]) if r.get("price") else 250000.0,
        "collateral_ratio": float(r["collateral_ratio"]) if r.get("collateral_ratio") else None,
        "closing_cost_ratio": float(tax) if tax else 0.02,
        "rejection_reasons": {x["reason"]: int(x["n"]) for x in reasons if x["reason"]},
    }


def _annuity(loan: float, rate_pct: float, years: int = LOAN_YEARS) -> float:
    i = rate_pct / 100 / 12
    n = years * 12
    return loan / n if i == 0 else loan * i / (1 - (1 + i) ** -n)


def _application(customer_id: str) -> dict[str, Any] | None:
    app = db.query_one("SELECT * FROM mortgages WHERE customer_id = ?", [customer_id])
    if app is None:
        return None
    events = db.query(
        "SELECT ts, event_type, note FROM mortgage_events WHERE mortgage_customer_id = ? "
        "AND event_type IN ('application_created','property_added','loan_calculation',"
        "'collateral_valuation','additional_collateral_requested','loan_decision') ORDER BY ts",
        [app["mortgage_customer_id"]],
    )
    reason = app.get("rejection_reason")
    return {
        "decision": app["final_decision"],
        "rejection_reason": reason,
        "lesson": _lesson(reason),
        "property_price": r2(app["final_property_price_eur"]),
        "requested_loan": r2(app["final_requested_loan_eur"]),
        "equity": r2(app["final_equity_amount_eur"]),
        "collateral_value": r2(app["final_collateral_value_eur"]),
        "required_monthly_income": r2(app["required_monthly_income_eur"]),
        "ltv": round(float(app["lfinal_loan_to_value"]), 4),
        "timeline": [{"date": e["ts"].date().isoformat() if e["ts"] else None,
                      "event": e["event_type"], "note": e["note"]} for e in events][:12],
    }


def _equity_estimate(customer_id: str) -> dict[str, float]:
    since = add_months(as_of(), -12)
    saved = db.scalar(
        "SELECT coalesce(sum(CASE WHEN category IN ('Invest Deposit','Salary Sweep') THEN -tx_amount_eur "
        "WHEN category = 'Invest Withdraw' THEN -tx_amount_eur ELSE 0 END), 0) FROM tx "
        "WHERE customer_id = ? AND tx_date > ?",
        [customer_id, since],
    )
    bal = current_balance(customer_id)
    return {"balance": bal, "savings_moved": float(saved or 0.0), "total": max(0.0, bal) + float(saved or 0.0)}


@ledger_cache()
def home_readiness(customer_id: str, property_price: float | None = None) -> dict[str, Any]:
    """Mortgage readiness check (see module docstring)."""
    db.ensure_customer(customer_id)
    ratios = dataset_ratios()
    application = _application(customer_id)
    if property_price is not None and float(property_price) <= 0:
        raise ValueError("property_price must be positive")
    price = float(property_price) if property_price else (
        application["property_price"] if application else ratios["median_price"])
    ltv = ratios["typical_ltv"]
    equity_needed = price * (1 - ltv)
    closing = price * ratios["closing_cost_ratio"]
    loan = price - equity_needed
    required_income = loan * ratios["income_per_loan_euro"]
    flows = monthly_flows(customer_id, 6)
    income = flows["income"]
    eq = _equity_estimate(customer_id)
    equity_have = eq["total"]

    gaps: list[str] = []
    equity_total_need = equity_needed + closing
    if equity_have < equity_total_need:
        missing = equity_total_need - equity_have
        months = (missing / flows["surplus"]) if flows["surplus"] > 0 else None
        m, eqn, cl = _n(missing), _n(equity_needed), _n(closing)
        gaps.append(tr(f"Down payment: about {m} € more needed (equity {eqn} € + closing costs {cl} €).",
                       f"Käsiraha: tarvitset noin {m} € lisää (omarahoitus {eqn} € + kaupanteon kulut {cl} €).",
                       f"Egen insats: ungefär {m} € till behövs (insats {eqn} € + kostnader vid köpet {cl} €).")
                    + (tr(f" At your current surplus that is ~{months:.0f} months of saving.",
                          f" Nykyisellä ylijäämälläsi se on noin {months:.0f} kuukauden säästäminen.",
                          f" Med ditt nuvarande överskott motsvarar det cirka {months:.0f} månaders sparande.")
                       if months else ""))
    if income < required_income:
        req, inc = _n(required_income), _n(income)
        gaps.append(tr(f"Income: banks in the dataset required about {req} €/month for this "
                       f"loan; you average {inc} €. A cheaper home or a co-applicant closes the gap.",
                       f"Tulot: aineiston pankit edellyttivät tälle lainalle noin {req} €/kk tuloja; "
                       f"sinun keskiarvosi on {inc} €. Edullisempi koti tai kanssahakija kuroo eron umpeen.",
                       f"Inkomst: bankerna i datamaterialet krävde ungefär {req} €/mån. för det här lånet; "
                       f"ditt genomsnitt är {inc} €. En billigare bostad eller en medsökande täpper till gapet."))
    if flows["surplus"] <= 0:
        gaps.append(tr("Monthly budget: spending currently exceeds income, which lenders read as risk. "
                       "A few months of positive surplus strengthens any application.",
                       "Kuukausibudjetti: menot ylittävät tällä hetkellä tulot, minkä lainanantaja näkee riskinä. "
                       "Muutama kuukausi plussalla vahvistaa mitä tahansa hakemusta.",
                       "Månadsbudget: utgifterna är just nu större än inkomsterna, vilket långivare ser som en risk. "
                       "Några månader med överskott stärker vilken ansökan som helst."))
    payment = _annuity(loan, RATE_PCT)
    stress = _annuity(loan, STRESS_RATE_PCT)
    if income > 0 and stress > 0.4 * income:
        st = _n(stress)
        gaps.append(tr(f"Stress test: at {STRESS_RATE_PCT:.0f} % interest the payment would be "
                       f"{st} €/month, over 40 % of your income.",
                       f"Stressitesti: {STRESS_RATE_PCT:.0f} %:n korolla erä olisi {st} €/kk, "
                       "yli 40 % tuloistasi.",
                       f"Stresstest: med {STRESS_RATE_PCT:.0f} % ränta skulle betalningen bli "
                       f"{st} €/mån., över 40 % av din inkomst."))
    if application and application["decision"] == "rejected" and application["rejection_reason"]:
        gaps.append(tr("Your earlier application: ", "Aiempi hakemuksesi: ", "Din tidigare ansökan: ")
                    + application["lesson"])

    eq_ok = equity_have >= equity_total_need
    inc_ok = income >= required_income
    if eq_ok and inc_ok and flows["surplus"] > 0:
        verdict = "ready"
    elif equity_have >= 0.75 * equity_total_need and income >= 0.85 * required_income:
        verdict = "almost"
    else:
        verdict = "not_yet"
    if verdict == "ready" and gaps:
        # e.g. an earlier rejection: the numbers look fine but there is still something to fix
        verdict = "almost"

    n_apps, n_ok, ltv_pct = ratios["applications"], ratios["approved"], f"{ltv * 100:.0f} %"
    inc_pct = f"{ratios['income_per_loan_euro'] * 100:.2f}"
    note = tr(f"Based on {n_apps} mortgage applications in the challenge dataset "
              f"({n_ok} approved). Approved loans had a median loan-to-value of "
              f"{ltv_pct}, and required monthly income was ≈ {inc_pct} % "
              f"of the loan. Educational estimate only: a real decision needs an S-Bank loan advisor.",
              f"Perustuu haasteaineiston {n_apps} asuntolainahakemukseen ({n_ok} hyväksytty). "
              f"Hyväksyttyjen lainojen lainan ja vakuuden suhteen mediaani oli {ltv_pct}, ja vaadittu "
              f"kuukausitulo oli ≈ {inc_pct.replace('.', ',')} % lainasta. Vain opetuksellinen arvio: "
              f"oikeaan päätökseen tarvitaan S-Pankin lainaneuvoja.",
              f"Baserat på {n_apps} ansökningar om bostadslån i utmaningens datamaterial ({n_ok} beviljade). "
              f"Beviljade lån hade en median för belåningsgrad på {ltv_pct}, och den krävda månadsinkomsten "
              f"var ≈ {inc_pct.replace('.', ',')} % av lånet. Endast en uppskattning i utbildningssyfte: ett "
              f"riktigt beslut kräver en lånerådgivare på S-Banken.")
    return {
        "property_price": r2(price),
        "loan_needed": r2(loan),
        "equity_needed": r2(equity_needed),
        "closing_costs_estimate": r2(closing),
        "your_equity_estimate": r2(equity_have),
        "equity_breakdown": {"balance": r2(eq["balance"]),
                             "moved_to_savings_12m": r2(eq["savings_moved"])},
        "required_monthly_income": r2(required_income),
        "your_monthly_income": r2(income),
        "ltv": round(ltv, 4),
        "monthly_payment_estimate": r2(payment),
        "stress_test_payment": r2(stress),
        "assumptions": {"loan_years": LOAN_YEARS, "rate_pct": RATE_PCT, "stress_rate_pct": STRESS_RATE_PCT},
        "verdict": verdict,
        "gaps": gaps,
        "dataset_note": note,
        "dataset_ratios": {k: v for k, v in ratios.items()},
        "customer_application": application,
    }
