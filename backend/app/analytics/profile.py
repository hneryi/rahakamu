"""Spender profile: a friendly, *transparent* archetype ("What kind of spender am I?").

Why archetypes
--------------
A label like "Latte Leaker ☕" is memorable and non-judgemental, which makes people curious
about the numbers behind it — exactly the teachable moment we want. But a black-box label
would erode trust, so every archetype is computed from visible trait scores.

Method
------
Eight behaviour traits are measured over the last 6 complete months (materialised for all
customers in :mod:`app.db` → ``customer_traits``). Each trait **score is a percentile
(0–100) among all 5 100 customers in the dataset**, so "82" literally means "more than 82 %
of customers":

==================  ==========================================================
savings power       1 − spending / income
leak share          leak basket / all spending
weekend share       share of leak spending on Fri–Sun
small treats        leak purchases under 15 € per week
big splurges        leak purchases over 100 € per month
late night          share of purchases between 22:00 and 05:00
steadiness          inverse of month-to-month spending volatility (CV)
cushion             lowest balance ÷ monthly spending
==================  ==========================================================

Archetype match scores are weighted averages led by each archetype's *defining* trait:

* ``tightrope_walker`` — forced to 100 when the balance closed below zero on ≥ 3 days;
  otherwise 0.7 × (100 − cushion).
* ``squirrel_saver``   — 0.5 savings power + 0.5 cushion
* ``impulse_splurger`` — 0.5 big splurges + 0.25 (100 − steadiness) + 0.25 late night
* ``latte_leaker``     — 0.6 small treats + 0.2 leak share + 0.2 (100 − savings power)
* ``weekend_treater``  — 0.7 weekend share + 0.3 leak share
* ``steady_planner``   — (steadiness + cushion + (100 − leak share)) / 3

(The savings term in *latte leaker* keeps a high saver with many tiny purchases from being
labelled a leaker: the small treats are not hurting them.)

The highest score wins; all scores are returned so the UI can show "runner-up" traits.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.analytics.common import r2
from app.i18n import eur, loc, tr

ARCHETYPES: dict[str, dict[str, str]] = {
    "steady_planner": {"name": "Steady Planner", "emoji": "🧭",
                       "description": "Your spending is calm and predictable and you keep a cushion. "
                                      "Next level: give every surplus euro a job (goal or investing)."},
    "weekend_treater": {"name": "Weekend Treater", "emoji": "🎉",
                        "description": "Weekdays are disciplined, weekends are for treats. A weekend "
                                       "budget lets you enjoy them without Monday regret."},
    "latte_leaker": {"name": "Latte Leaker", "emoji": "☕",
                     "description": "Lots of small everyday purchases that add up quietly. Each one "
                                    "is tiny; together they are a real monthly bill."},
    "impulse_splurger": {"name": "Impulse Splurger", "emoji": "⚡",
                         "description": "Occasional big, spontaneous purchases make your months swing. "
                                        "A 48-hour wait rule tames the spikes."},
    "squirrel_saver": {"name": "Squirrel Saver", "emoji": "🐿️",
                       "description": "You save a big share of income and keep leaks small. Make sure "
                                      "your savings work for you, and enjoy a planned treat too."},
    "tightrope_walker": {"name": "Tightrope Walker", "emoji": "🎪",
                         "description": "Your balance often runs close to (or below) zero before payday. "
                                        "A small buffer is your superpower move."},
}

#: Localised archetype names and descriptions (``emoji`` and ``key`` are shared).
ARCHETYPES_L10N: dict[str, dict[str, tuple[str, str]]] = {
    "fi": {
        "steady_planner": ("Suunnitelmallinen", "Kulutuksesi on rauhallista ja ennakoitavaa, ja sinulla on pelivaraa. "
                           "Seuraava taso: anna jokaiselle ylijäävälle eurolle tehtävä (tavoite tai sijoittaminen)."),
        "weekend_treater": ("Viikonloppuherkuttelija", "Arkena olet kurinalainen, viikonloppu on herkuttelua varten. "
                            "Viikonloppubudjetilla voit nauttia ilman maanantain katumusta."),
        "latte_leaker": ("Lattevuotaja", "Paljon pieniä arjen ostoksia, jotka kertyvät hiljaa. Yksittäin pieniä, "
                         "yhdessä ne ovat oikea kuukausilasku."),
        "impulse_splurger": ("Heräteostelija", "Välillä tulee isoja, spontaaneja ostoksia, jotka heiluttavat kuukausiasi. "
                             "48 tunnin odotussääntö tasoittaa piikit."),
        "squirrel_saver": ("Oravasäästäjä", "Säästät ison osan tuloistasi ja pidät vuodot pieninä. Varmista, että "
                           "säästösi tekevät töitä puolestasi, ja nauti myös suunnitellusta herkusta."),
        "tightrope_walker": ("Nuorallatanssija", "Saldosi käy usein lähellä nollaa (tai alle) ennen palkkapäivää. "
                             "Pieni puskuri on sinun supervoimasi."),
    },
    "sv": {
        "steady_planner": ("Den stadiga planeraren", "Dina utgifter är lugna och förutsägbara och du har en marginal. "
                           "Nästa nivå: ge varje överbliven euro ett jobb (ett sparmål eller placeringar)."),
        "weekend_treater": ("Helgnjutaren", "Vardagarna är disciplinerade, helgerna är till för att unna sig. "
                            "En helgbudget gör att du kan njuta utan måndagsånger."),
        "latte_leaker": ("Latteläckaren", "Många små vardagsköp som växer i det tysta. Vart och ett är litet, "
                         "tillsammans blir de en riktig månadsräkning."),
        "impulse_splurger": ("Impulsköparen", "Ibland blir det stora, spontana köp som får månaderna att svänga. "
                             "En regel om att vänta 48 timmar jämnar ut topparna."),
        "squirrel_saver": ("Ekorrspararen", "Du sparar en stor del av inkomsten och håller läckorna små. Se till att "
                           "sparpengarna arbetar för dig, och unna dig också något planerat."),
        "tightrope_walker": ("Lindansaren", "Ditt saldo går ofta nära noll (eller under) före lönedagen. "
                             "En liten buffert är ditt superdrag."),
    },
}

TRAITS: list[tuple[str, str, str]] = [
    # key, label, percentile column
    ("savings_power", "Savings power", "p_savings_rate"),
    ("leak_share", "Leak share", "p_leak_share"),
    ("weekend", "Weekend spending", "p_weekend_share"),
    ("small_treats", "Small treats", "p_small_tx"),
    ("big_splurges", "Big splurges", "p_big_leaks"),
    ("night_owl", "Late-night purchases", "p_late_night"),  # key kept for API compatibility
    ("steadiness", "Steadiness", "p_steadiness"),
    ("cushion", "Cushion", "p_cushion"),
]


_TRAIT_LABELS_L10N: dict[str, dict[str, str]] = {
    "fi": {"savings_power": "Säästövoima", "leak_share": "Vuotojen osuus", "weekend": "Viikonloppukulutus",
           "small_treats": "Pienet herkut", "big_splurges": "Isot hairahdukset", "night_owl": "Myöhäisillan ostokset",
           "steadiness": "Tasaisuus", "cushion": "Pelivara"},
    "sv": {"savings_power": "Sparkraft", "leak_share": "Andel läckor", "weekend": "Helgutgifter",
           "small_treats": "Små guldkanter", "big_splurges": "Stora snedsteg", "night_owl": "Sena kvällsköp",
           "steadiness": "Stabilitet", "cushion": "Marginal"},
}


def _trait_label(key: str, en: str) -> str:
    current = loc()
    return en if current == "en" else _TRAIT_LABELS_L10N[current].get(key, en)


def _archetype(key: str) -> dict[str, str]:
    base = {"key": key, **ARCHETYPES[key]}
    current = loc()
    if current != "en":
        base["name"], base["description"] = ARCHETYPES_L10N[current][key]
    return base


def _pct0(value: float) -> str:
    return f"{value * 100:.0f} %"


def _detail(key: str, t: dict[str, Any]) -> str:
    if loc() != "en":
        return _detail_l10n(key, t)
    if key == "savings_power":
        return f"You keep {t['savings_rate'] * 100:.0f} % of your income after spending."
    if key == "leak_share":
        return f"{t['leak_share'] * 100:.0f} % of your spending is in the everyday-leaks basket."
    if key == "weekend":
        return f"{t['weekend_share'] * 100:.0f} % of leak spending happens Friday to Sunday."
    if key == "small_treats":
        return f"About {t['small_tx_per_week']:.1f} small (< 15 €) leak purchases a week."
    if key == "big_splurges":
        return f"About {t['big_leaks_per_month']:.1f} leak purchases over 100 € a month."
    if key == "night_owl":
        return f"{t['late_night_share'] * 100:.0f} % of purchases happen between 22:00 and 05:00."
    if key == "steadiness":
        return f"Monthly spending varies by about {t['volatility'] * 100:.0f} % month to month."
    if key == "cushion":
        if t["days_below_zero"]:
            return f"Your balance closed below zero on {int(t['days_below_zero'])} day(s) in 6 months."
        return f"Your lowest balance was {t['min_balance']:.0f} €."
    return ""


def _detail_l10n(key: str, t: dict[str, Any]) -> str:
    """Finnish / Swedish trait details (same numbers as :func:`_detail`)."""
    dec = (lambda v: f"{v:.1f}".replace(".", ","))
    if key == "savings_power":
        return tr("", f"Sinulle jää {_pct0(t['savings_rate'])} tuloistasi kulutuksen jälkeen.",
                  f"Du behåller {_pct0(t['savings_rate'])} av din inkomst efter utgifterna.")
    if key == "leak_share":
        return tr("", f"{_pct0(t['leak_share'])} kulutuksestasi on arjen vuotoja.",
                  f"{_pct0(t['leak_share'])} av dina utgifter ligger i korgen vardagsläckor.")
    if key == "weekend":
        return tr("", f"{_pct0(t['weekend_share'])} vuotokulutuksesta osuu perjantaista sunnuntaihin.",
                  f"{_pct0(t['weekend_share'])} av läckorna sker fredag till söndag.")
    if key == "small_treats":
        return tr("", f"Noin {dec(t['small_tx_per_week'])} pientä (< 15 €) vuoto-ostosta viikossa.",
                  f"Ungefär {dec(t['small_tx_per_week'])} små (< 15 €) läckköp i veckan.")
    if key == "big_splurges":
        return tr("", f"Noin {dec(t['big_leaks_per_month'])} yli 100 € vuoto-ostosta kuukaudessa.",
                  f"Ungefär {dec(t['big_leaks_per_month'])} läckköp över 100 € i månaden.")
    if key == "night_owl":
        return tr("", f"{_pct0(t['late_night_share'])} ostoksista tehdään klo 22–05.",
                  f"{_pct0(t['late_night_share'])} av köpen görs mellan kl. 22 och 05.")
    if key == "steadiness":
        return tr("", f"Kuukausikulutuksesi vaihtelee noin {_pct0(t['volatility'])} kuukaudesta toiseen.",
                  f"Dina månadsutgifter varierar med ungefär {_pct0(t['volatility'])} från månad till månad.")
    if key == "cushion":
        if t["days_below_zero"]:
            n = int(t["days_below_zero"])
            return tr("", f"Saldosi oli päivän päätteeksi miinuksella {n} päivänä 6 kuukauden aikana.",
                      f"Ditt saldo var på minus vid dagens slut {n} dag(ar) under 6 månader.")
        return tr("", f"Pienin saldosi oli {eur(t['min_balance'], 0)}.", f"Ditt lägsta saldo var {eur(t['min_balance'], 0)}.")
    return ""


@ledger_cache()
def spender_profile(customer_id: str) -> dict[str, Any]:
    """Archetype + transparent trait scores (see module docstring)."""
    db.ensure_customer(customer_id)
    t = db.query_one("SELECT * FROM customer_traits WHERE customer_id = ?", [customer_id])
    if t is None:  # customer with no activity in the window
        t = {k: 0 for k in ("savings_rate", "leak_share", "weekend_share", "small_tx_per_week",
                            "big_leaks_per_month", "late_night_share", "volatility",
                            "days_below_zero", "min_balance", "cushion_months")}
        t.update({col: 50 for _, _, col in TRAITS})
    s = {key: int(t[col]) for key, _, col in TRAITS}
    scores = {
        "tightrope_walker": 100.0 if t["days_below_zero"] >= 3 else 0.7 * (100 - s["cushion"]),
        "squirrel_saver": 0.5 * s["savings_power"] + 0.5 * s["cushion"],
        "impulse_splurger": (0.5 * s["big_splurges"] + 0.25 * (100 - s["steadiness"])
                             + 0.25 * s["night_owl"]),
        "latte_leaker": (0.6 * s["small_treats"] + 0.2 * s["leak_share"]
                         + 0.2 * (100 - s["savings_power"])),
        "weekend_treater": 0.7 * s["weekend"] + 0.3 * s["leak_share"],
        "steady_planner": (s["steadiness"] + s["cushion"] + 100 - s["leak_share"]) / 3,
    }
    key = max(scores, key=lambda k: scores[k])
    arch = _archetype(key)
    if t["days_below_zero"] >= 3:
        n = int(t["days_below_zero"])
        rule = tr(f"Your balance closed below zero on {n} days in the last 6 months, so the tightrope comes first.",
                  f"Saldosi oli päivän päätteeksi miinuksella {n} päivänä viimeisen 6 kuukauden aikana, "
                  "joten nuorallatanssi menee kaiken muun edelle.",
                  f"Ditt saldo var på minus vid dagens slut {n} dagar under de senaste 6 månaderna, "
                  "så lindansen kommer först.")
    else:
        rule = tr(f"Highest match score: {arch['name']} ({scores[key]:.0f}/100). Scores "
                  "are weighted averages of the trait percentiles shown below.",
                  f"Korkein osumapistemäärä: {arch['name']} ({scores[key]:.0f}/100). Pisteet ovat "
                  "alla näkyvien piirteiden persentiilien painotettuja keskiarvoja.",
                  f"Högsta matchningspoäng: {arch['name']} ({scores[key]:.0f}/100). Poängen är "
                  "viktade medelvärden av percentilerna för egenskaperna nedan.")
    return {
        "archetype": arch,
        "traits": [{"key": k, "label": _trait_label(k, label), "score": s[k], "detail": _detail(k, t)}
                   for k, label, _ in TRAITS],
        "archetype_scores": {k: round(v, 1) for k, v in sorted(scores.items(), key=lambda x: -x[1])},
        "rule": rule,
        "savings_rate": round(float(t["savings_rate"]), 4),
        "leak_share": round(float(t["leak_share"]), 4),
        "weekend_share": round(float(t["weekend_share"]), 4),
        "small_tx_per_week": round(float(t["small_tx_per_week"]), 2),
        "late_night_share": round(float(t["late_night_share"]), 4),
        "volatility": round(float(t["volatility"]), 4),
        "big_purchases_per_month": round(float(t["big_leaks_per_month"]), 2),
        "days_below_zero": int(t["days_below_zero"]),
        "min_balance": r2(t["min_balance"]),
        "method": tr("Trait scores are percentiles among all customers in the dataset (last 6 full months).",
                     "Piirteiden pisteet ovat persentiilejä kaikkien aineiston asiakkaiden joukossa "
                     "(viimeiset 6 täyttä kuukautta).",
                     "Egenskapspoängen är percentiler bland alla kunder i datamaterialet "
                     "(de senaste 6 hela månaderna)."),
    }
