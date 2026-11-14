"""Savings goals: CRUD plus the goal planner ("Help me save for a car that costs 12 000 €").

Pedagogy
--------
A goal turns "I should save" into a number per month, and the planner answers the two
questions people actually have: *Is this realistic with how I live now?* and *What would I
have to change?* The answer is always grounded in the customer's own data:

* ``current_monthly_surplus`` = average monthly income − spending over the last 6 complete
  months (money already moved to savings counts as surplus: it can be redirected), minus
  what other active goals already claim.
* ``needed_per_month`` = (target − saved) / months until the deadline.
* ``gap`` = needed − surplus (≥ 0; a *negative* surplus widens it, an overspender must first
  close the deficit). If there is a gap we propose **cuts**, mostly from the
  *leak* basket, using realistic per-category cut percentages (eating out 30 %, taxis 50 %,
  entertainment 25 %, lifestyle 30 %, kiosk/convenience 40 %, travel 20 %, gadgets 25 %),
  biggest euro impact first, until the gap is covered.
* ``feasibility``: ``on_track`` (no gap), ``stretch`` (cuts cover the gap),
  ``unrealistic`` (even the cuts are not enough → ``suggested_deadline`` shows when it *is*
  reachable).
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from app import db, store
from app.config import settings
from app.analytics.cache import ledger_cache
from app.i18n import day, eur, loc, tr
from app.analytics.common import (
    add_months,
    as_of,
    full_months_window,
    monthly_flows,
    parse_date,
    r2,
)

GOAL_KINDS: tuple[str, ...] = ("car", "travel", "home", "emergency", "education", "gadget", "other")
KIND_EMOJI: dict[str, str] = {"car": "🚗", "travel": "✈️", "home": "🏡", "emergency": "🛟",
                              "education": "🎓", "gadget": "💻", "other": "🎯"}

#: Leak-basket groups the planner may suggest cutting: (key, label, SQL predicate, cut %, why)
CUT_GROUPS: list[tuple[str, str, str, int, str]] = [
    ("restaurants", "Eating out", "category = 'Restaurants'", 30,
     "Cooking at home a few more times a week is the easiest big win."),
    ("taxi", "Taxis", "category = 'Transportation' AND mcc_code = 4121", 50,
     "Swap half of the rides for public transport or a bike."),
    ("entertainment", "Entertainment", "category = 'Entertainment'", 25,
     "Keep the favourites, drop the 'just because' tickets and extras."),
    ("lifestyle", "Shopping & lifestyle", "category = 'Lifestyle'", 30,
     "Try a 48-hour wait before non-essential purchases."),
    ("convenience", "Kiosk & convenience stores", "category = 'Groceries' AND mcc_code = 5499", 40,
     "Kiosk prices are high; plan the weekly shop instead."),
    ("travel", "Travel", "category = 'Travel'", 20,
     "Book earlier, travel off-season, or make one trip a bit shorter."),
    ("gadgets", "Gadgets & home buys", "category = 'Home & Tech'", 25,
     "Delay upgrades: a phone or gadget that still works can wait."),
]


#: key → (label, why) for fi / sv; index-aligned by key with :data:`CUT_GROUPS`.
CUT_GROUPS_L10N: dict[str, dict[str, tuple[str, str]]] = {
    "fi": {
        "restaurants": ("Ulkona syöminen", "Kotona kokkaaminen muutaman kerran useammin viikossa on helpoin iso voitto."),
        "taxi": ("Taksit", "Vaihda puolet kyydeistä joukkoliikenteeseen tai pyörään."),
        "entertainment": ("Viihde", "Pidä suosikit, jätä pois 'ihan muuten vaan' -liput ja lisät."),
        "lifestyle": ("Ostokset ja vapaa-aika", "Kokeile 48 tunnin odotusta ennen ei-välttämättömiä ostoksia."),
        "convenience": ("Kioskit ja lähikaupat", "Kioskihinnat ovat korkeat; suunnittele viikon ruokaostokset."),
        "travel": ("Matkailu", "Varaa aiemmin, matkusta sesongin ulkopuolella tai lyhennä yhtä matkaa vähän."),
        "gadgets": ("Laitteet ja kodin hankinnat", "Lykkää päivityksiä: toimiva puhelin tai laite voi odottaa."),
    },
    "sv": {
        "restaurants": ("Äta ute", "Att laga mat hemma några gånger till i veckan är den enklaste stora vinsten."),
        "taxi": ("Taxi", "Byt ut hälften av resorna mot kollektivtrafik eller cykel."),
        "entertainment": ("Nöjen", "Behåll favoriterna, hoppa över biljetter och extra köpta 'bara för att'."),
        "lifestyle": ("Shopping och fritid", "Prova att vänta 48 timmar före köp som inte är nödvändiga."),
        "convenience": ("Kiosker och närbutiker", "Kioskpriserna är höga; planera veckans matinköp i stället."),
        "travel": ("Resor", "Boka tidigare, res utanför säsong eller korta av en resa lite."),
        "gadgets": ("Prylar och heminköp", "Skjut upp uppgraderingar: en telefon eller pryl som fungerar kan vänta."),
    },
}


class GoalNotFound(KeyError):
    """Raised for an unknown goal id (routers map it to HTTP 404)."""


#: Seeded demo goal names (store.SEED_GOALS) in fi / sv. A goal whose stored name is one of
#: these English seed names is shown in the request locale; user-typed names never change.
SEED_NAME_L10N: dict[str, tuple[str, str]] = {
    "Emergency fund": ("Puskurirahasto", "Buffert"),
    "New laptop": ("Uusi läppäri", "Ny dator"),
    "Summer trip": ("Kesämatka", "Sommarresa"),
    "Electric car": ("Sähköauto", "Elbil"),
    "Home down payment": ("Asunnon käsiraha", "Egen insats för bostad"),
    "Trip with the grandkids": ("Matka lastenlasten kanssa", "Resa med barnbarnen"),
    "Back in the black": ("Takaisin plussalle", "Tillbaka på plus"),
}


def _display_name(name: str) -> str:
    pair = SEED_NAME_L10N.get(name)
    return tr(name, pair[0], pair[1]) if pair else name


def _shape(row: dict[str, Any]) -> dict[str, Any]:
    target = float(row["target_amount"])
    saved = float(row["saved_amount"] or 0.0)
    deadline = row.get("deadline")
    months_left = None
    if deadline:
        months_left = store.months_between(as_of(), date.fromisoformat(deadline))
    return {
        "id": row["id"],
        "name": _display_name(row["name"]),
        "emoji": row.get("emoji") or KIND_EMOJI.get(row.get("kind") or "other", "🎯"),
        "kind": row.get("kind") or "other",
        "target_amount": r2(target),
        "saved_amount": r2(saved),
        "deadline": deadline,
        "monthly_contribution": r2(row.get("monthly_contribution")),
        "progress": round(min(1.0, saved / target), 4) if target > 0 else 0.0,
        "remaining": r2(max(0.0, target - saved)),
        "months_left": months_left,
        "created_at": row.get("created_at"),
    }


def _clean_kind(kind: str | None) -> str:
    k = (kind or "other").strip().lower()
    return k if k in GOAL_KINDS else "other"


def _clean_deadline(deadline: str | date | None) -> str | None:
    d = parse_date(deadline)
    return d.isoformat() if d else None


#: Largest euro amount a goal field may hold (also enforced by the request models).
MAX_AMOUNT = 10_000_000.0


def _amount(value: Any, field: str) -> float:
    """A finite euro amount within ``0 … MAX_AMOUNT`` or a ``ValueError`` (→ HTTP 422).

    The chat agent calls these functions directly, so the bounds cannot live only in the
    HTTP request models: ``1e308 + 1e308`` is infinity, which is not valid JSON.
    """
    try:
        amount = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(tr(f"{field} must be a number", f"{field}: arvon on oltava luku",
                            f"{field} måste vara ett tal")) from exc
    if not math.isfinite(amount) or amount < 0 or amount > MAX_AMOUNT:
        limit = eur(MAX_AMOUNT, 0)
        raise ValueError(tr(f"{field} must be between 0 and {limit}",
                            f"{field}: arvon on oltava välillä 0 – {limit}",
                            f"{field} måste vara mellan 0 och {limit}"))
    return amount


def _clean_name(name: Any) -> str:
    """Goal names are shown in the app and quoted to the AI coach: keep them plain text.

    Control characters and angle brackets are dropped, whitespace is collapsed and the
    length is capped at 80 characters.
    """
    text = "".join(" " if ch.isspace() else ch for ch in str(name or ""))  # tabs and line breaks separate words
    text = "".join(ch for ch in text if ch.isprintable() and ch not in "<>")
    text = " ".join(text.split())[:80].strip()
    if not text:
        raise ValueError(tr("Goal name is required", "Tavoitteen nimi on pakollinen", "Målets namn är obligatoriskt"))
    return text


def _clean_emoji(emoji: Any) -> str | None:
    text = "".join(ch for ch in str(emoji or "") if ch.isprintable() and not ch.isalnum() and ch not in "<>\"'&" and not ch.isspace())
    return text[:8] or None


def list_goals(customer_id: str) -> list[dict[str, Any]]:
    """All goals of a customer (seeded demo goals included)."""
    db.ensure_customer(customer_id)
    return [_shape(r) for r in store.goal_rows(customer_id)]


def create_goal(customer_id: str, name: str, target_amount: float, deadline: str | None = None,
                emoji: str | None = None, kind: str = "other", saved_amount: float = 0.0) -> dict[str, Any]:
    """Create a goal. ``monthly_contribution`` is derived from the deadline (0 without one)."""
    db.ensure_customer(customer_id)
    clean_name = _clean_name(name)
    target = _amount(target_amount, "target_amount")
    saved = _amount(saved_amount or 0.0, "saved_amount")
    if target <= 0:
        raise ValueError("target_amount must be positive")
    limit = int(settings.max_goals_per_customer)
    if 0 < limit <= store.goal_count(customer_id):
        raise ValueError(tr(f"You already have {limit} goals, which is the maximum. Delete one to add another.",
                            f"Sinulla on jo {limit} tavoitetta, mikä on enimmäismäärä. Poista yksi lisätäksesi uuden.",
                            f"Du har redan {limit} mål, vilket är det högsta antalet. Ta bort ett för att lägga till ett nytt."))
    dl = _clean_deadline(deadline)
    k = _clean_kind(kind)
    monthly = 0.0
    if dl:
        monthly = max(0.0, target - saved) / store.months_between(as_of(), date.fromisoformat(dl))
    row = store.insert_goal({
        "customer_id": customer_id, "name": clean_name, "emoji": _clean_emoji(emoji) or KIND_EMOJI[k],
        "kind": k, "target_amount": target, "saved_amount": saved, "deadline": dl,
        "monthly_contribution": round(monthly, 2),
    })
    return _shape(row)


def update_goal(customer_id: str, goal_id: str, **fields: Any) -> dict[str, Any]:
    """Patch a goal. Accepts any of name, emoji, kind, target_amount, saved_amount, deadline,
    monthly_contribution, plus ``add_amount`` (deposit towards the goal)."""
    db.ensure_customer(customer_id)
    current = store.goal_row(customer_id, goal_id)
    if current is None:
        raise GoalNotFound(goal_id)
    patch: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
    if "add_amount" in patch:
        try:
            deposit = float(patch.pop("add_amount"))
        except (TypeError, ValueError) as exc:
            raise ValueError(tr("add_amount must be a number", "add_amount: arvon on oltava luku",
                                "add_amount måste vara ett tal")) from exc
        if not math.isfinite(deposit):
            deposit = MAX_AMOUNT * 10  # rejected by the range check just below
        patch["saved_amount"] = float(current["saved_amount"]) + deposit
    if "name" in patch:
        patch["name"] = _clean_name(patch["name"])
    if "emoji" in patch:
        patch["emoji"] = _clean_emoji(patch["emoji"]) or current.get("emoji")
    if "kind" in patch:
        patch["kind"] = _clean_kind(patch["kind"])
    if "deadline" in patch:
        patch["deadline"] = _clean_deadline(patch["deadline"])
    for k in ("target_amount", "saved_amount", "monthly_contribution"):
        if k in patch:
            patch[k] = _amount(patch[k], k)
            if k == "target_amount" and patch[k] == 0:
                raise ValueError(f"{k} must be positive")
    store.update_goal_row(customer_id, goal_id, patch)
    row = store.goal_row(customer_id, goal_id)
    assert row is not None
    return _shape(row)


def delete_goal(customer_id: str, goal_id: str) -> dict[str, Any]:
    db.ensure_customer(customer_id)
    if not store.delete_goal_row(customer_id, goal_id):
        raise GoalNotFound(goal_id)
    return {"deleted": True, "id": goal_id}


@ledger_cache()
def leak_cut_candidates(customer_id: str, months: int = 6) -> list[dict[str, Any]]:
    """Monthly average per cut group (leak basket only) with the realistic cut, biggest first."""
    start, end = full_months_window(months)
    out: list[dict[str, Any]] = []
    for key, label, pred, pct, why in CUT_GROUPS:
        # ``pred`` is a constant from CUT_GROUPS above, never user input.
        v = db.scalar(
            f"SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx WHERE customer_id = ? "
            f"AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 AND basket = 'leak' AND ({pred})",
            [customer_id, start, end],
        )
        monthly = float(v or 0.0) / months
        if monthly < 5:
            continue
        category = pred.split("'")[1]
        if loc() != "en":
            label, why = CUT_GROUPS_L10N[loc()][key]
        out.append({"key": key, "label": label, "category": category, "basket": "leak",
                    "current_monthly": r2(monthly), "cut_pct": pct,
                    "monthly_saving": r2(monthly * pct / 100), "why": why})
    out.sort(key=lambda c: -c["monthly_saving"])
    return out


def plan_goal(customer_id: str, target_amount: float, deadline: str | None = None,
              name: str | None = None, saved_amount: float = 0.0) -> dict[str, Any]:
    """Plan a savings goal against the customer's real surplus (see module docstring)."""
    db.ensure_customer(customer_id)
    target = float(target_amount)
    saved = float(saved_amount or 0.0)
    if target <= 0:
        raise ValueError("target_amount must be positive")
    today = as_of()
    remaining = max(0.0, target - saved)
    flows = monthly_flows(customer_id, 6)
    committed = sum(g["monthly_contribution"] for g in list_goals(customer_id)
                    if g["progress"] < 1 and (name is None or g["name"].lower() != name.lower()))
    surplus = flows["surplus"] - committed
    available = max(0.0, surplus)
    candidates = leak_cut_candidates(customer_id)

    dl = parse_date(deadline)
    if dl is not None and dl <= today:
        raise ValueError("deadline must be in the future")
    if dl is None:
        # No deadline: aim for 12 months, or sooner if the surplus allows.
        months_by_surplus = int(-(-remaining // available)) if available > 0 else 12
        months = max(1, min(12, months_by_surplus))
        dl = add_months(today, months)
    else:
        months = store.months_between(today, dl)
    needed = remaining / months
    gap = max(0.0, needed - surplus)  # signed: a monthly deficit has to be closed too

    cuts: list[dict[str, Any]] = []
    covered = 0.0
    if gap > 0:
        for c in candidates:
            if covered >= gap:
                break
            cuts.append(c)
            covered += c["monthly_saving"]
    else:  # on track: show up to two optional accelerators
        optional = tr(" (optional: reach the goal sooner)", " (valinnainen: saavutat tavoitteen nopeammin)",
                      " (valfritt: du når målet snabbare)")
        cuts = [dict(c, why=c["why"] + optional) for c in candidates[:2]]
        covered = sum(c["monthly_saving"] for c in cuts)
    cuts_total = sum(c["monthly_saving"] for c in cuts)

    if gap <= 0:
        feasibility = "on_track"
    elif cuts_total >= gap:
        feasibility = "stretch"
    else:
        feasibility = "unrealistic"

    capacity = surplus + sum(c["monthly_saving"] for c in candidates)
    if capacity > 0:
        months_needed = max(1, int(-(-remaining // capacity)))
        suggested = add_months(today, months_needed).isoformat()
    else:
        suggested = None
    if feasibility != "unrealistic":
        suggested = dl.isoformat() if feasibility == "on_track" else suggested

    goal_name = name or tr("Your goal", "Tavoitteesi", "Ditt mål")
    need, avail = eur(needed, 0), eur(available, 0)
    trims = ", ".join(c["label"].lower() for c in cuts)
    if feasibility == "on_track":
        summary = tr(f"{goal_name}: save {need}/month for {months} months. Your current "
                     f"surplus of about {avail}/month already covers it.",
                     f"{goal_name}: säästä {need}/kk {months} kuukauden ajan. Nykyinen noin "
                     f"{avail}/kk ylijäämäsi riittää jo siihen.",
                     f"{goal_name}: spara {need}/mån. i {months} månader. Ditt nuvarande "
                     f"överskott på ungefär {avail}/mån. räcker redan till det.")
    elif feasibility == "stretch" and surplus < 0:
        short = eur(-surplus, 0)
        summary = tr(f"{goal_name}: you need {need}/month, and right now about {short}/month more goes "
                     f"out than comes in. Trimming {trims} closes the whole {eur(gap, 0)} gap.",
                     f"{goal_name}: tarvitset {need}/kk, ja tällä hetkellä rahaa lähtee noin {short}/kk "
                     f"enemmän kuin tulee. Karsimalla näitä ({trims}) kurot koko {eur(gap, 0)} eron umpeen.",
                     f"{goal_name}: du behöver {need}/mån., och just nu går det ut ungefär {short}/mån. mer "
                     f"än det kommer in. Genom att dra ner på {trims} täpper du till hela gapet på {eur(gap, 0)}.")
    elif feasibility == "stretch":
        summary = tr(f"{goal_name}: you need {need}/month but have about {avail} "
                     f"spare. Trimming {trims} closes the {eur(gap, 0)} gap.",
                     f"{goal_name}: tarvitset {need}/kk, mutta ylimääräistä on noin {avail}. "
                     f"Karsimalla näitä ({trims}) kurot {eur(gap, 0)} eron umpeen.",
                     f"{goal_name}: du behöver {need}/mån. men har ungefär {avail} "
                     f"över. Genom att dra ner på {trims} täpper du till gapet på {eur(gap, 0)}.")
    else:
        later = tr(f"A deadline around {day(suggested)} would be realistic.",
                   f"Realistinen takaraja olisi noin {day(suggested)}.",
                   f"Ett realistiskt slutdatum vore runt {day(suggested)}.") if suggested else tr(
            "Start by building a small monthly surplus first.",
            "Aloita kerryttämällä ensin pieni kuukausittainen ylijäämä.",
            "Börja med att först bygga upp ett litet månatligt överskott.")
        if surplus < 0:
            short = eur(-surplus, 0)
            incl = tr(" (your other goals included)", " (muut tavoitteesi mukaan lukien)",
                      " (dina andra mål inräknade)") if committed > 0 else ""
            summary = tr(f"{goal_name}: it would take {need}/month, but right now about {short}/month more "
                         f"goes out than comes in{incl}. Realistic cuts ({eur(cuts_total, 0)}) are not "
                         f"enough yet. ",
                         f"{goal_name}: tarvittaisiin {need}/kk, mutta tällä hetkellä rahaa lähtee noin "
                         f"{short}/kk enemmän kuin tulee{incl}. Realistiset leikkaukset "
                         f"({eur(cuts_total, 0)}) eivät vielä riitä. ",
                         f"{goal_name}: det skulle kräva {need}/mån., men just nu går det ut ungefär "
                         f"{short}/mån. mer än det kommer in{incl}. Realistiska nedskärningar "
                         f"({eur(cuts_total, 0)}) räcker inte ännu. ") + later
        else:
            summary = tr(f"{goal_name}: {need}/month is more than your surplus "
                         f"({avail}) plus realistic cuts ({eur(cuts_total, 0)}). ",
                         f"{goal_name}: {need}/kk on enemmän kuin ylijäämäsi ({avail}) ja "
                         f"realistiset leikkaukset ({eur(cuts_total, 0)}) yhteensä. ",
                         f"{goal_name}: {need}/mån. är mer än ditt överskott ({avail}) plus "
                         f"realistiska nedskärningar ({eur(cuts_total, 0)}). ") + later
    return {
        "name": goal_name,
        "target_amount": r2(target),
        "saved_amount": r2(saved),
        "remaining": r2(remaining),
        "deadline": dl.isoformat(),
        "months": months,
        "needed_per_month": r2(needed),
        "current_monthly_surplus": r2(surplus),
        "monthly_income": flows["income"],
        "monthly_spending": flows["spending"],
        "committed_to_other_goals": r2(committed),
        "gap": r2(gap),
        "feasibility": feasibility,
        "suggested_deadline": suggested,
        "cuts": [{k: c[k] for k in ("label", "category", "basket", "current_monthly", "cut_pct",
                                     "monthly_saving", "why")} for c in cuts],
        "cuts_total": r2(cuts_total),
        "summary": summary,
    }
