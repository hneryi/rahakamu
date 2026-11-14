"""The three baskets — SPankkiBot's core money-literacy model (SPEC §2).

Pedagogy
--------
Budgets fail when people treat every euro the same. We teach one simple mental model and
use it everywhere (home meter, chat answers, lessons):

1. **Fixed essentials** (``fixed``) — mandatory *and* regular: rent, utilities, everyday
   groceries, public transport, anything that hits on a steady monthly rhythm.
   *Plan once, then automate.*
2. **Irregular essentials** (``irregular``) — mandatory but lumpy: health, repairs,
   car costs, a big one-off grocery haul. *They feel like surprises but are predictable on
   average, so you save a small buffer every month.*
3. **Everyday leaks** (``leak``) — discretionary spending that slips through your fingers:
   eating out, taxis, kiosks, entertainment, shopping, travel. *This is where change is
   cheapest; small cuts here compound.*

Non-spending flows are tagged ``income`` (salary, other income, investment withdrawals)
and ``saving`` (investment deposits, salary sweeps to savings).

Single source of truth
----------------------
:func:`classify_sql` is the **only** definition of the rules. It is evaluated once when the
``tx`` table is materialised (see :mod:`app.db`), so every endpoint, the agent and the tests
read the same ``basket`` column. :func:`classify` is a line-by-line Python mirror used for
single rows and verified against SQL in the test-suite. :data:`RULES` holds the plain-language
"why" behind each rule so the UI and the agent can always explain a classification.
"""

from __future__ import annotations

from typing import Any

from app import db
from app.analytics.cache import ledger_cache
from app.analytics.common import (
    SPENDING_BASKETS,
    basket_label,
    add_months,
    as_of,
    month_start,
    r2,
)
from app.analytics.labels import category_default_label, mcc_label
from app.i18n import loc

FIXED_GROCERY_MCC = (5411, 5422, 5451)  # supermarket, butcher, dairy
REPAIR_MCC = (5200, 5251)  # home supply, hardware
CAR_MCC = (5541, 5542, 7523)  # service station, fuel, parking
TRANSIT_MCC = 4111
TAXI_MCC = 4121
CONVENIENCE_MCC = 5499
HOME_TECH_IRREGULAR_EUR = 150.0
CAR_IRREGULAR_EUR = 80.0

#: Plain-language explanation of each basket (shown on tap in the BasketMeter).
EXPLANATIONS: dict[str, str] = {
    "fixed": (
        "Fixed essentials are the must-pay bills that come back every month: rent, "
        "utilities, everyday groceries and public transport, plus any payment we detected "
        "repeating monthly at a steady amount. You can't skip them, but you can plan for "
        "them on payday and automate them."
    ),
    "irregular": (
        "Irregular essentials are necessary but lumpy: health and pharmacy, home repairs, "
        "bigger tech or home purchases (over 150 €), car costs such as fuel fill-ups and "
        "parking over 80 €, and one-off unusually large essential purchases. They feel like "
        "surprises, but on average they are predictable, so set aside a small buffer monthly."
    ),
    "leak": (
        "Everyday leaks are the flexible, often small purchases that slip through your "
        "fingers: eating out, cafés and bars, kiosks, taxis, entertainment, shopping, "
        "gadgets and travel. Nothing wrong with enjoying them, but this is the basket where "
        "a small change saves the most money with the least pain."
    ),
}

#: Ordered rule list (mirrors the CASE branches) with the human 'why'.
RULES: list[dict[str, str]] = [
    {"basket": "income", "rule": "Salary, other income, investment withdrawals", "why": "Money coming in."},
    {"basket": "saving", "rule": "Investment deposits, salary sweeps to savings", "why": "Money you set aside for future you."},
    {"basket": "fixed", "rule": "Housing and utilities", "why": "Must-pay bills that repeat every month."},
    {"basket": "irregular", "rule": "All health spending", "why": "Necessary, but timing and size vary."},
    {"basket": "irregular", "rule": "Home & Tech at hardware/home-supply stores, or any Home & Tech purchase over 150 €", "why": "Repairs and bigger home/tech needs are lumpy."},
    {"basket": "irregular", "rule": "Fuel, service stations or parking over 80 €", "why": "Car costs arrive in chunks."},
    {"basket": "irregular", "rule": "One-off essential purchase over 3x your usual ticket (and over 120 €)", "why": "An unusual spike in an essential category."},
    {"basket": "fixed", "rule": "A merchant you pay roughly monthly at a stable amount (CV < 0.25)", "why": "Behaves like a subscription or standing bill."},
    {"basket": "fixed", "rule": "Groceries at supermarkets, butchers, dairy shops", "why": "Everyday food is a regular essential."},
    {"basket": "fixed", "rule": "Public transport", "why": "Getting to work and school is a regular essential."},
    {"basket": "leak", "rule": "Everything else: restaurants, cafés, bars, kiosks, taxis, entertainment, lifestyle, travel, gadgets", "why": "Flexible spending you control day to day."},
]


EXPLANATIONS_L10N: dict[str, dict[str, str]] = {
    "en": EXPLANATIONS,
    "fi": {
        "fixed": (
            "Kiinteät välttämättömät ovat pakollisia laskuja, jotka palaavat joka kuukausi: vuokra, "
            "asumisen laskut, arjen ruokaostokset ja joukkoliikenne sekä maksut, jotka toistuvat "
            "kuukausittain lähes samansuuruisina. Niitä ei voi jättää väliin, mutta ne voi "
            "suunnitella palkkapäivänä ja automatisoida."
        ),
        "irregular": (
            "Epäsäännölliset välttämättömät ovat tarpeellisia mutta epätasaisia: terveys ja apteekki, "
            "kodin korjaukset, isommat tekniikka- ja kodinhankinnat (yli 150 €), autokulut kuten "
            "yli 80 € tankkaukset ja pysäköinnit sekä yksittäiset tavallista suuremmat välttämättömät "
            "ostokset. Ne tuntuvat yllätyksiltä, mutta keskimäärin ne ovat ennustettavia, joten varaa "
            "niihin pieni puskuri joka kuukausi."
        ),
        "leak": (
            "Arjen vuodot ovat joustavia, usein pieniä ostoksia, jotka valuvat sormien läpi: ulkona "
            "syöminen, kahvilat ja baarit, kioskit, taksit, viihde, shoppailu, laitteet ja matkat. "
            "Niistä saa nauttia, mutta juuri tässä korissa pieni muutos säästää eniten rahaa "
            "vähimmällä vaivalla."
        ),
    },
    "sv": {
        "fixed": (
            "Fasta måsten är räkningar som måste betalas och som kommer tillbaka varje månad: hyra, "
            "boenderäkningar, vardagliga matinköp och kollektivtrafik, plus betalningar som vi har sett "
            "återkomma varje månad med ett jämnt belopp. Du kan inte hoppa över dem, men du kan "
            "planera dem på lönedagen och automatisera dem."
        ),
        "irregular": (
            "Oregelbundna måsten är nödvändiga men ojämna: hälsa och apotek, reparationer i hemmet, "
            "större teknik- och heminköp (över 150 €), bilkostnader som tankningar och parkering över "
            "80 € och enstaka ovanligt stora nödvändiga köp. De känns som överraskningar, men i "
            "genomsnitt går de att förutse, så lägg undan en liten buffert varje månad."
        ),
        "leak": (
            "Vardagsläckor är flexibla, ofta små köp som rinner mellan fingrarna: äta ute, kaféer och "
            "barer, kiosker, taxi, nöjen, shopping, prylar och resor. Det är inget fel att njuta av "
            "dem, men det är i den här korgen som en liten förändring sparar mest pengar med minst möda."
        ),
    },
}

#: (rule, why) per locale, index-aligned with :data:`RULES`.
_RULES_L10N: dict[str, list[tuple[str, str]]] = {
    "fi": [
        ("Palkka, muut tulot, sijoitusten nostot", "Sisään tuleva raha."),
        ("Sijoitustalletukset ja palkasta säästöön tehtävät siirrot", "Raha, jonka laitat sivuun tulevalle itsellesi."),
        ("Asuminen ja asumisen laskut", "Pakolliset laskut, jotka toistuvat joka kuukausi."),
        ("Kaikki terveysmenot", "Välttämättömiä, mutta ajoitus ja summa vaihtelevat."),
        ("Koti ja tekniikka -ostokset rauta- ja kodintarvikeliikkeistä sekä kaikki yli 150 € koti- ja tekniikkaostokset",
         "Korjaukset ja isommat koti- ja tekniikkatarpeet tulevat epätasaisesti."),
        ("Polttoaine, huoltoasemat tai pysäköinti yli 80 €", "Autokulut tulevat isoina erinä."),
        ("Yksittäinen välttämätön ostos, joka on yli 3 kertaa tavallista ostostasi suurempi (ja yli 120 €)",
         "Poikkeuksellinen piikki välttämättömässä kategoriassa."),
        ("Kauppias, jolle maksat noin kerran kuussa vakaan summan (CV < 0,25)", "Toimii kuin tilaus tai kestomaksu."),
        ("Ruokaostokset supermarketeista, liha- ja maitokaupoista", "Arjen ruoka on säännöllinen välttämättömyys."),
        ("Joukkoliikenne", "Työ- ja koulumatkat ovat säännöllinen välttämättömyys."),
        ("Kaikki muu: ravintolat, kahvilat, baarit, kioskit, taksit, viihde, ostokset, matkat, laitteet",
         "Joustavaa kulutusta, jota ohjaat itse päivittäin."),
    ],
    "sv": [
        ("Lön, övriga inkomster, uttag från placeringar", "Pengar som kommer in."),
        ("Insättningar till placeringar, överföringar av lönen till sparande", "Pengar som du lägger undan åt ditt framtida jag."),
        ("Boende och boenderäkningar", "Räkningar som måste betalas och återkommer varje månad."),
        ("Alla hälsoutgifter", "Nödvändiga, men tidpunkt och belopp varierar."),
        ("Hem och teknik från järnhandlar och butiker för hemförnödenheter, eller alla köp inom hem och teknik över 150 €",
         "Reparationer och större behov för hem och teknik kommer ojämnt."),
        ("Bränsle, bensinstationer eller parkering över 80 €", "Bilkostnader kommer i klumpar."),
        ("Enstaka nödvändigt köp som är över 3 gånger ditt vanliga köp (och över 120 €)",
         "En ovanlig topp i en nödvändig kategori."),
        ("En handlare som du betalar ungefär en gång i månaden med ett stabilt belopp (CV < 0,25)",
         "Fungerar som en prenumeration eller en stående räkning."),
        ("Matinköp i matbutiker, kött- och mejeributiker", "Vardagsmat är ett regelbundet måste."),
        ("Kollektivtrafik", "Resor till jobb och skola är ett regelbundet måste."),
        ("Allt annat: restauranger, kaféer, barer, kiosker, taxi, nöjen, shopping, resor, prylar",
         "Flexibel konsumtion som du själv styr dag för dag."),
    ],
}


def explanations() -> dict[str, str]:
    """Basket explanations in the current request locale."""
    return dict(EXPLANATIONS_L10N[loc()])


def rules() -> list[dict[str, str]]:
    """Classification rules with their 'why', in the current request locale."""
    current = loc()
    if current == "en":
        return [dict(r) for r in RULES]
    return [{"basket": r["basket"], "rule": rule, "why": why}
            for r, (rule, why) in zip(RULES, _RULES_L10N[current], strict=True)]


def classify_sql() -> str:
    """SQL CASE expression producing the basket for a ``tx`` row.

    Requires columns ``category``, ``mcc_code``, ``tx_amount_eur``, ``is_recurring``,
    ``is_outlier`` (the last two are computed in :mod:`app.db`). Branch order matters and
    matches :data:`RULES` and :func:`classify`.
    """
    g = ", ".join(map(str, FIXED_GROCERY_MCC))
    rep = ", ".join(map(str, REPAIR_MCC))
    car = ", ".join(map(str, CAR_MCC))
    return f"""CASE
        WHEN category IN ('Salary', 'Other Income', 'Invest Withdraw') THEN 'income'
        WHEN category IN ('Invest Deposit', 'Salary Sweep') THEN 'saving'
        WHEN tx_amount_eur > 0 THEN 'income'
        WHEN category IN ('Housing', 'Utilities') THEN 'fixed'
        WHEN category = 'Health' THEN 'irregular'
        WHEN category = 'Home & Tech' AND (mcc_code IN ({rep})
             OR -tx_amount_eur > {HOME_TECH_IRREGULAR_EUR}) THEN 'irregular'
        WHEN category = 'Transportation' AND mcc_code IN ({car})
             AND -tx_amount_eur > {CAR_IRREGULAR_EUR} THEN 'irregular'
        WHEN coalesce(is_outlier, false) AND coalesce(mcc_code, 0) NOT IN ({CONVENIENCE_MCC}, {TAXI_MCC})
             THEN 'irregular'
        WHEN coalesce(is_recurring, false) THEN 'fixed'
        WHEN category = 'Groceries' AND (mcc_code IS NULL OR mcc_code IN ({g})) THEN 'fixed'
        WHEN category = 'Transportation' AND mcc_code = {TRANSIT_MCC} THEN 'fixed'
        ELSE 'leak'
    END"""


def classify(row: dict[str, Any]) -> str:
    """Python mirror of :func:`classify_sql` for a single row-like dict."""
    cat = row.get("category")
    mcc = row.get("mcc_code", row.get("mcc"))
    mcc = int(mcc) if mcc is not None else None
    amt = float(row.get("tx_amount_eur", row.get("amount", 0.0)) or 0.0)
    out = -amt
    if cat in ("Salary", "Other Income", "Invest Withdraw"):
        return "income"
    if cat in ("Invest Deposit", "Salary Sweep"):
        return "saving"
    if amt > 0:
        return "income"
    if cat in ("Housing", "Utilities"):
        return "fixed"
    if cat == "Health":
        return "irregular"
    if cat == "Home & Tech" and (mcc in REPAIR_MCC or out > HOME_TECH_IRREGULAR_EUR):
        return "irregular"
    if cat == "Transportation" and mcc in CAR_MCC and out > CAR_IRREGULAR_EUR:
        return "irregular"
    if row.get("is_outlier") and (mcc or 0) not in (CONVENIENCE_MCC, TAXI_MCC):
        return "irregular"
    if row.get("is_recurring"):
        return "fixed"
    if cat == "Groceries" and (mcc is None or mcc in FIXED_GROCERY_MCC):
        return "fixed"
    if cat == "Transportation" and mcc == TRANSIT_MCC:
        return "fixed"
    return "leak"


def _group_label(category: str, mcc: int | None) -> str:
    """Label for 'top items' inside a basket: MCC description, else category label."""
    if mcc is not None:
        return mcc_label(mcc) or category
    return category_default_label(category)


@ledger_cache()
def get_baskets(customer_id: str, months: int = 6) -> dict[str, Any]:
    """Monthly basket split for the last ``months`` calendar months (the as-of month last,
    partial), the current month's top contributors per basket, and the explanations.

    Totals are positive euros. ``fixed + irregular + leak`` equals total spending.
    """
    db.ensure_customer(customer_id)
    months = max(1, min(int(months), 24))
    today = as_of()
    cur_start = month_start(today)
    start = add_months(cur_start, -(months - 1))
    rows = db.query(
        "SELECT strftime(tx_date, '%Y-%m') AS ym, basket, sum(abs(tx_amount_eur)) AS total, "
        "count(*) AS n FROM tx WHERE customer_id = ? AND tx_date BETWEEN ? AND ? "
        "GROUP BY ALL",
        [customer_id, start, today],
    )
    by_month: dict[str, dict[str, Any]] = {}
    m = start
    while m <= cur_start:
        ym = m.strftime("%Y-%m")
        by_month[ym] = {"month": ym, "fixed": 0.0, "irregular": 0.0, "leak": 0.0,
                        "income": 0.0, "saving": 0.0, "tx_count": 0}
        m = add_months(m, 1)
    for r in rows:
        rec = by_month.get(r["ym"])
        if rec is not None:
            rec[r["basket"]] = r2(r["total"])
            rec["tx_count"] += int(r["n"])
    month_list = list(by_month.values())
    for rec in month_list:
        rec["spent"] = r2(sum(rec[b] for b in SPENDING_BASKETS))
        rec["partial"] = rec["month"] == cur_start.strftime("%Y-%m")

    current = dict(month_list[-1])
    top_rows = db.query(
        "SELECT basket, category, mcc_code, sum(-tx_amount_eur) AS total, count(*) AS n FROM tx "
        "WHERE customer_id = ? AND tx_date BETWEEN ? AND ? AND tx_amount_eur < 0 "
        "AND basket IN ('fixed','irregular','leak') GROUP BY ALL",
        [customer_id, cur_start, today],
    )
    top: dict[str, dict[str, dict[str, Any]]] = {b: {} for b in SPENDING_BASKETS}
    for r in top_rows:
        mcc = int(r["mcc_code"]) if r["mcc_code"] is not None else None
        label = _group_label(r["category"], mcc)
        item = top[r["basket"]].setdefault(
            label, {"label": label, "category": r["category"], "total": 0.0, "count": 0})
        item["total"] += float(r["total"])
        item["count"] += int(r["n"])
    current["top"] = {
        b: [dict(i, total=r2(i["total"])) for i in
            sorted(top[b].values(), key=lambda x: -x["total"])[:5]]
        for b in SPENDING_BASKETS
    }
    spent = current["spent"] or 0.0
    current["shares"] = {b: (round(current[b] / spent, 3) if spent else 0.0)
                         for b in SPENDING_BASKETS}
    complete = [mm for mm in month_list if not mm["partial"]]
    avg = {b: r2(sum(mm[b] for mm in complete) / len(complete)) if complete else 0.0
           for b in (*SPENDING_BASKETS, "income", "saving")}
    return {
        "months": month_list,
        "current_month": current,
        "average_complete_month": avg,
        "explanations": explanations(),
        "labels": {b: basket_label(b) for b in SPENDING_BASKETS},
        "rules": rules(),
    }
