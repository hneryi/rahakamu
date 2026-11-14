"""Benchmarks: "How do I compare with people like me?"

Two complementary reference points, both shown with their source:

1. **Peers in the dataset** — customers in the same age band (18–29, 30–39, …, 70+; the
   18–19 year-olds are merged into 18–29 so the youngest band is not tiny). For every
   spending category we report the peer median, the 25th/75th percentile and *your*
   percentile (share of peers who spend less than you; ties count half). Window: the last
   6 complete months, precomputed in :mod:`app.db` (``peer_category`` / ``peer_flows``).
2. **Statistics Finland** — official national figures from ``app/data/benchmarks_fi.json``
   (Household Budget Survey per consumption unit by age group, median disposable income by
   age, household saving rate). The file is curated separately and parsed defensively: if it
   is missing or a figure is absent, ``stat_fi_monthly`` is simply ``None``.

Pedagogy: a percentile is a *mirror, not a verdict*. The dataset is synthetic and national
averages hide huge variation, so the agent is instructed to use these numbers as a reality
check ("you spend more on eating out than 80 % of people your age") rather than a judgement.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.i18n import loc, tr
from app.analytics.common import r2
from app.config import APP_DATA_DIR

log = logging.getLogger(__name__)

SPEND_CATEGORIES: tuple[str, ...] = (
    "Housing", "Groceries", "Utilities", "Transportation", "Restaurants", "Entertainment",
    "Lifestyle", "Health", "Home & Tech", "Travel",
)
_BAND_RE = re.compile(r"^\D*(\d+)\s*[-–]\s*(\d+)\D*$")
_PLUS_RE = re.compile(r"^\D*(\d+)\s*\+$")


def age_band(age: int) -> tuple[int, int | None, str]:
    """(low, high, label) of the dataset peer band for an age."""
    if age < 30:
        return 18, 29, "18–29"
    if age >= 70:
        return 70, None, "70+"
    low = (age // 10) * 10
    return low, low + 9, f"{low}–{low + 9}"


@lru_cache(maxsize=1)
def _fi() -> dict[str, Any]:
    path = APP_DATA_DIR / "benchmarks_fi.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        log.warning("benchmarks_fi.json unreadable: %s", exc)
        return {}


def _band_for(bands: Any, age: int) -> dict[str, Any] | None:
    """Pick the entry of a ``{"17-24": {...}, "85+": {...}}`` mapping that contains ``age``."""
    if not isinstance(bands, dict):
        return None
    for key, val in bands.items():
        if not isinstance(val, dict):
            continue
        k = str(key).strip()
        m = _BAND_RE.match(k)
        if m and int(m.group(1)) <= age <= int(m.group(2)):
            return val
        m = _PLUS_RE.match(k)
        if m and age >= int(m.group(1)) and not k.lower().startswith("adult"):
            return val
    return None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def stat_fi_category(category: str, age: int) -> float | None:
    """Statistics Finland monthly euros per person for a dataset category, or ``None``."""
    fi = _fi()
    band = _band_for(fi.get("by_age_group"), age)
    for container in (
        (band or {}).get("monthly_per_consumption_unit_eur"),
        (band or {}).get("monthly_per_person_eur"),
        fi.get("monthly_per_person_eur"),
        fi.get("monthly_per_consumption_unit_eur"),
    ):
        if isinstance(container, dict) and _num(container.get(category)) is not None:
            return r2(container[category])
    return None


def stat_fi_income(age: int) -> float | None:
    inc = _fi().get("income")
    if not isinstance(inc, dict):
        return None
    band = _band_for(inc.get("by_age_group"), age) or {}
    for k in ("median_personal_disposable_income_month_eur",
              "median_disposable_cash_income_per_consumption_unit_month_eur"):
        if _num(band.get(k)) is not None:
            return r2(band[k])
    return None


def stat_fi_saving_rate() -> float | None:
    sr = _fi().get("saving_rate")
    if not isinstance(sr, dict):
        return None
    latest = sr.get("latest")
    if isinstance(latest, dict) and _num(latest.get("pct")) is not None:
        return round(float(latest["pct"]) / 100, 4)
    if _num(sr.get("average_2025_pct")) is not None:
        return round(float(sr["average_2025_pct"]) / 100, 4)
    return None


#: Finnish / Swedish source names and notes (the data file's own texts are English).
_SOURCE_L10N: dict[str, dict[str, tuple[str, str]]] = {
    "fi": {
        "income": ("Tilastokeskus, tulonjakotilasto, taulukko tjt/14k5",
                   "Käytettävissä olevien rahatulojen mediaani kulutusyksikköä kohden ikäryhmässä; kuukausi = vuosi / 12."),
        "saving_rate": ("Tilastokeskus, sektoreiden neljännesvuositilinpito, taulukko ntp/15a8, kotitaloudet (S14)",
                        "Kotitalouksien säästämisaste = bruttosäästö prosentteina käytettävissä olevista tuloista "
                        "(kansantalouden tilinpito). Koko maan luku, ei suoraan vertailukelpoinen yksittäisen "
                        "pankkiasiakkaan säästöasteen kanssa, mutta hyvä vertailukohta."),
    },
    "sv": {
        "income": ("Statistikcentralen, inkomstfördelningsstatistik, tabell tjt/14k5",
                   "Median för disponibla penninginkomster per konsumtionsenhet i åldersgruppen; månad = år / 12."),
        "saving_rate": ("Statistikcentralen, sektorräkenskaper per kvartal, tabell ntp/15a8, hushåll (S14)",
                        "Hushållens sparkvot = bruttosparande i procent av disponibel inkomst "
                        "(nationalräkenskaper). En siffra för hela landet, inte direkt jämförbar med en enskild "
                        "bankkunds sparkvot, men en bra referenspunkt."),
    },
}


def _sources() -> list[dict[str, str]]:
    fi = _fi()
    current = loc()
    out = [{"name": tr("Rahakamu peer group (synthetic Junction 2026 dataset)",
                       "Rahakamun vertailuryhmä (synteettinen Junction 2026 -aineisto)",
                       "Rahakamus jämförelsegrupp (syntetiskt Junction 2026-datamaterial)"), "url": "",
            "note": tr("Customers in the same age band, last 6 complete months.",
                       "Saman ikäryhmän asiakkaat, viimeiset 6 täyttä kuukautta.",
                       "Kunder i samma åldersgrupp, de senaste 6 hela månaderna.")}]
    meta = fi.get("meta") if isinstance(fi.get("meta"), dict) else {}
    if meta:
        tables = meta.get("tables") if isinstance(meta.get("tables"), dict) else {}
        year = meta.get("year", "")
        out.append({"name": tr(str(meta.get("source", "Statistics Finland")),
                               "Tilastokeskus, StatFin-tietokanta (avoin PxWeb-rajapinta)",
                               "Statistikcentralen, databasen StatFin (öppet PxWeb-gränssnitt)"),
                    "url": str(tables.get("consumption_by_age") or meta.get("url", "")),
                    "note": tr(f"Household Budget Survey {year}, per consumption unit "
                               f"(= per person for a single-person household). {meta.get('license', '')}".strip(),
                               f"Kulutustutkimus {year}, kulutusyksikköä kohden (= henkeä kohden yhden hengen "
                               "taloudessa). CC BY 4.0 — lähde: Tilastokeskus",
                               f"Konsumtionsundersökningen {year}, per konsumtionsenhet (= per person i ett "
                               "enpersonshushåll). CC BY 4.0 — källa: Statistikcentralen")})
    for key in ("income", "saving_rate"):
        sec = fi.get(key)
        if isinstance(sec, dict) and sec.get("source"):
            url = ""
            if isinstance(meta.get("tables"), dict):
                url = meta["tables"].get("income_by_age" if key == "income" else "household_saving_rate", "")
            name, note = str(sec["source"]), str(sec.get("definition") or sec.get("notes") or "")[:300]
            if current != "en":
                name, note = _SOURCE_L10N[current][key]
            out.append({"name": name, "url": str(url), "note": note})
    return out


def _percentile(values: list[float], you: float) -> int:
    if not values:
        return 50
    below = sum(1 for v in values if v < you)
    ties = sum(1 for v in values if v == you)
    return int(round(100 * (below + 0.5 * ties) / len(values)))


def _quantiles(values: list[float]) -> tuple[float, float, float]:
    if not values:
        return 0.0, 0.0, 0.0
    vs = sorted(values)

    def q(p: float) -> float:
        idx = p * (len(vs) - 1)
        lo, hi = int(idx), min(int(idx) + 1, len(vs) - 1)
        return vs[lo] + (vs[hi] - vs[lo]) * (idx - lo)

    return q(0.25), q(0.5), q(0.75)


@ledger_cache()
def benchmarks(customer_id: str) -> dict[str, Any]:
    """Peer-group and Statistics Finland comparison (see module docstring)."""
    cust = db.get_customer(customer_id)
    age = int(cust["age"])
    low, high, label = age_band(age)
    band_sql = "age >= ?" + (" AND age <= ?" if high is not None else "")
    band_params: list[Any] = [low] + ([high] if high is not None else [])

    flows = db.query(f"SELECT customer_id, income, spending, saving FROM peer_flows WHERE {band_sql}",
                     band_params)
    peer_ids = {f["customer_id"] for f in flows}
    cat_rows = db.query(
        f"SELECT pc.customer_id, pc.category, pc.monthly FROM peer_category pc "
        f"JOIN peer_flows pf USING (customer_id) WHERE {band_sql.replace('age', 'pf.age')}",
        band_params,
    )
    by_cat: dict[str, dict[str, float]] = {c: {} for c in SPEND_CATEGORIES}
    for r in cat_rows:
        if r["category"] in by_cat:
            by_cat[r["category"]][r["customer_id"]] = float(r["monthly"])

    categories = []
    for cat in SPEND_CATEGORIES:
        vals_map = by_cat[cat]
        values = [vals_map.get(pid, 0.0) for pid in peer_ids]  # zero for peers without spend
        you = vals_map.get(customer_id, 0.0)
        p25, med, p75 = _quantiles(values)
        categories.append({
            "category": cat,
            "you_monthly": r2(you),
            "peer_median_monthly": r2(med),
            "peer_p25": r2(p25),
            "peer_p75": r2(p75),
            "percentile": _percentile(values, you),
            "stat_fi_monthly": stat_fi_category(cat, age),
        })

    me = next((f for f in flows if f["customer_id"] == customer_id),
              {"income": 0.0, "spending": 0.0, "saving": 0.0})
    incomes = [float(f["income"]) for f in flows]
    p25, med, p75 = _quantiles(incomes)
    income = {"category": "Income", "you_monthly": r2(me["income"]), "peer_median_monthly": r2(med),
              "peer_p25": r2(p25), "peer_p75": r2(p75),
              "percentile": _percentile(incomes, float(me["income"])),
              "stat_fi_monthly": stat_fi_income(age)}

    def rate(f: dict[str, Any]) -> float:
        inc = float(f["income"])
        return (inc - float(f["spending"])) / inc if inc > 0 else 0.0

    rates = [rate(f) for f in flows]
    p25, med, p75 = _quantiles(rates)
    savings_rate = {"you": round(rate(me), 4), "peer_median": round(med, 4),
                    "peer_p25": round(p25, 4), "peer_p75": round(p75, 4),
                    "percentile": _percentile(rates, rate(me)),
                    "stat_fi": stat_fi_saving_rate(),
                    "note": tr("Savings rate = 1 − spending / income. Statistics Finland figure is the "
                               "national household saving rate (gross saving / disposable income).",
                               "Säästöaste = 1 − menot / tulot. Tilastokeskuksen luku on koko maan kotitalouksien "
                               "säästämisaste (bruttosäästö / käytettävissä olevat tulot).",
                               "Sparkvot = 1 − utgifter / inkomst. Statistikcentralens siffra är hushållens "
                               "sparkvot i hela landet (bruttosparande / disponibel inkomst).")}

    biggest_gap = max(categories, key=lambda c: c["you_monthly"] - c["peer_median_monthly"])
    return {
        "peer_group": {"label": tr(f"Age {label} in dataset", f"Ikä {label} aineistossa",
                                   f"Ålder {label} i datamaterialet"), "size": len(peer_ids),
                       "age_band": label, "your_age": age},
        "categories": categories,
        "income": income,
        "savings_rate": savings_rate,
        "highlight": {
            "category": biggest_gap["category"],
            "you_monthly": biggest_gap["you_monthly"],
            "peer_median_monthly": biggest_gap["peer_median_monthly"],
            "percentile": biggest_gap["percentile"],
        },
        "sources": _sources(),
    }
