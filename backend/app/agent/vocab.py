"""Shared vocabulary: categories, baskets, sub-categories, synonyms, periods, formatting.

Why a vocabulary module
-----------------------
The LLM path (tool schemas) and the offline fallback (keyword router) must understand
the *same* words — "taxi", "taksi", "dining out", "ulkona syöminen", "äta ute" — and map them to the
dataset's canonical categories and MCC codes. Keeping that mapping in one place means
the two paths cannot drift apart, and the enum values in the JSON schemas give the model
a closed, valid set of choices (no hallucinated category names reaching SQL).

Periods are resolved here too. Letting the model pick ``period="last_month"`` instead of
computing ISO dates itself removes a whole class of date-arithmetic mistakes; the
resolution is relative to the pinned ``AS_OF_DATE`` so every answer is reproducible.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

SPENDING_CATEGORIES: tuple[str, ...] = (
    "Groceries",
    "Restaurants",
    "Transportation",
    "Utilities",
    "Entertainment",
    "Health",
    "Home & Tech",
    "Housing",
    "Lifestyle",
    "Travel",
)
INCOME_CATEGORIES: tuple[str, ...] = ("Salary", "Other Income", "Invest Withdraw")
SAVING_CATEGORIES: tuple[str, ...] = ("Invest Deposit", "Salary Sweep")
ALL_CATEGORIES: tuple[str, ...] = SPENDING_CATEGORIES + INCOME_CATEGORIES + SAVING_CATEGORIES

BASKETS: tuple[str, ...] = ("fixed", "irregular", "leak", "income", "saving")
GROUP_BY: tuple[str, ...] = ("none", "category", "basket", "month", "week", "weekday", "merchant", "hour", "day")

#: Friendly sub-categories → (parent category, MCC codes). Lets users ask about "taxis"
#: or "fast food" even though the dataset category is broader.
SUBCATEGORIES: dict[str, tuple[str, tuple[int, ...]]] = {
    "taxi": ("Transportation", (4121,)),
    "public_transport": ("Transportation", (4111,)),
    "fuel": ("Transportation", (5541, 5542)),
    "parking": ("Transportation", (7523,)),
    "restaurants": ("Restaurants", (5812,)),
    "fast_food_cafes": ("Restaurants", (5814,)),
    "bars": ("Restaurants", (5813,)),
    "supermarket": ("Groceries", (5411,)),
    "convenience_store": ("Groceries", (5499,)),
    "pharmacy": ("Health", (5912,)),
    "doctor": ("Health", (8011, 8099)),
    "dentist": ("Health", (8021,)),
    "electronics": ("Home & Tech", (5732, 5734)),
    "furniture": ("Home & Tech", (5712,)),
    "hardware_diy": ("Home & Tech", (5200, 5251)),
    "cinema": ("Entertainment", (7832,)),
    "concerts_events": ("Entertainment", (7922,)),
    "recreation": ("Entertainment", (7999, 7991, 7996)),
    "clothing": ("Lifestyle", (5651, 5691)),
    "sports_gear": ("Lifestyle", (5941,)),
    "books_hobbies": ("Lifestyle", (5942, 5945)),
    "flights": ("Travel", (4511,)),
    "hotels": ("Travel", (7011,)),
    "car_rental": ("Travel", (7512,)),
}

#: Keyword (lower-case, en + fi + sv stems) → ("category"|"subcategory"|"basket", value).
#: Order matters: more specific phrases first.
SYNONYMS: list[tuple[str, tuple[str, str]]] = [
    (r"\btax(i|is|ies)\b|\btaks[ie]|\btaxi(n|resor|resa|bil)|\buber\b|\bbolt\b", ("subcategory", "taxi")),
    (r"public transport|\bbus(es)?\b|\btram|\bmetro\b|\btrain|joukkoliikenne|\bbussi|\bratikka|\bjuna|kollektivtrafik|lokaltrafik|\bbuss|spårvagn|\btåg", ("subcategory", "public_transport")),
    (r"\bfuel\b|\bpetrol\b|\bgas station|\bbensa|polttoaine|tankkau|\bbensin|bränsle|\btanka", ("subcategory", "fuel")),
    (r"\bparking\b|pysäköin|parkki|parkering", ("subcategory", "parking")),
    (r"fast food|\bcaf[eé]s?\b|coffee|latte|pikaruoka|kahvi|\bkaffe|\bkafé|snabbmat|\bfika", ("subcategory", "fast_food_cafes")),
    (r"\bbars?\b|\bpubs?\b|nightlife|\bbaari|\bkapakk|yöelämä|\bbar(er|en|erna)\b|\bkrog|\bpubar|uteliv|nattliv", ("subcategory", "bars")),
    (r"convenience|kiosk|\bkioski|r-kioski|lähikauppa|närbutik", ("subcategory", "convenience_store")),
    (r"pharmac|apteek|apotek", ("subcategory", "pharmacy")),
    (r"dentist|hammaslää|tandläk", ("subcategory", "dentist")),
    (r"\bcinema|\bmovies?\b|elokuv|leffa|\bbio\b|biograf|biobesök", ("subcategory", "cinema")),
    (r"concert|konsert|keikka|teatter|theat|\bteater", ("subcategory", "concerts_events")),
    (r"cloth|fashion|vaate|vaatt|muoti|\bkläder|klädinköp", ("subcategory", "clothing")),
    (r"flight|lento|\bflyg", ("subcategory", "flights")),
    (r"hotel|hotell", ("subcategory", "hotels")),
    (r"electronic|elektroniik|elektronik|\bgadget", ("subcategory", "electronics")),
    (r"dining out|eating out|eat out|restaurant|takeaway|take-away|delivery|deliveries|ravintol|ulkona syö|noutoruoka|ruokalähet|restaurang|äta ute|äter ute|ätit ute|uteätande|hämtmat|matleverans|\bwolt|\bfoodora", ("category", "Restaurants")),
    (r"grocer|food shop|supermarket|ruokaostok|ruokakaup|kauppaostok|päivittäistavar|\bruoka|\bruoa|livsmedel|matbutik|mataffär|matinköp|matvaror|dagligvar|\bmat(en)?\b", ("category", "Groceries")),
    (r"transport|commut|liikenne|liikkumi|matkakulu|pendl|\btrafik|resekostnad", ("category", "Transportation")),
    (r"utilit|electricity|\bwater bill|internet bill|sähkö|vesilasku|\blasku|elräkning|\bel(en)?\b|vattenräkning|\bräkning", ("category", "Utilities")),
    (r"entertain|fun money|hobbies|viihde|viihte|huvi|\bnöje|underhållning", ("category", "Entertainment")),
    (r"health|medical|doctor|tervey|lääkär|\bhälsa|\bhälso|\bläkar|sjukvård", ("category", "Health")),
    (r"home & tech|home and tech|furniture|kodin|huonekalu|tekniikka|möbler|inredning|hemelektronik|hem och teknik", ("category", "Home & Tech")),
    (r"\brent\b|housing|mortgage payment|vuokra|asumi|vastike|\bhyra|\bboende|vederlag", ("category", "Housing")),
    (r"lifestyle|shopping|shop\b|ostoksi|shoppail|\bshoppa|\binköp", ("category", "Lifestyle")),
    (r"travel|holiday|vacation|trip|matkailu|matkoihin|loma|matka|\bres(a|an|or|orna)\b|\bsemester|utlandsres", ("category", "Travel")),
    (r"leak|discretionary|vuod|turha|läck|onödig", ("basket", "leak")),
    (r"irregular|epäsäännöll|oregelbund", ("basket", "irregular")),
    (r"fixed cost|fixed basket|essential|kiinte|pakollis|fasta utgift|fasta kostnad|fasta nödvändig|fasta måsten|nödvändiga utgift", ("basket", "fixed")),
    (r"subscription|tilaus|tilauks|recurring|toistuv|prenumeration|abonnemang|återkommande", ("basket", "fixed")),
]

CATEGORY_FI: dict[str, str] = {
    "Groceries": "ruokaostokset",
    "Restaurants": "ravintolat",
    "Transportation": "liikkuminen",
    "Utilities": "asumisen laskut",
    "Entertainment": "viihde",
    "Health": "terveys",
    "Home & Tech": "koti ja tekniikka",
    "Housing": "asuminen",
    "Lifestyle": "ostokset ja vapaa-aika",
    "Travel": "matkailu",
    "Salary": "palkka",
    "Other Income": "muut tulot",
    "Invest Deposit": "sijoitukset",
    "Salary Sweep": "säästösiirrot",
    "Invest Withdraw": "sijoitusnostot",
}
CATEGORY_SV: dict[str, str] = {
    "Groceries": "matinköp",
    "Restaurants": "restauranger",
    "Transportation": "transport",
    "Utilities": "boenderäkningar",
    "Entertainment": "nöjen",
    "Health": "hälsa",
    "Home & Tech": "hem och teknik",
    "Housing": "boende",
    "Lifestyle": "shopping",
    "Travel": "resor",
    "Salary": "lön",
    "Other Income": "övriga inkomster",
    "Invest Deposit": "placeringar",
    "Salary Sweep": "sparöverföringar",
    "Invest Withdraw": "uttag från placeringar",
}
#: Finnish "…kulujasi" stems for status lines ("Tarkistan ravintolakulujasi…").
CATEGORY_FI_STEM: dict[str, str] = {
    "Groceries": "ruokakauppa",
    "Restaurants": "ravintola",
    "Transportation": "liikkumis",
    "Utilities": "sähkö- ja vesi",
    "Entertainment": "viihde",
    "Health": "terveys",
    "Home & Tech": "koti- ja tekniikka",
    "Housing": "asumis",
    "Lifestyle": "shoppailu",
    "Travel": "matka",
}
SUBCATEGORY_LABEL: dict[str, dict[str, str]] = {
    "taxi": {"en": "taxi", "fi": "taksi", "sv": "taxi"},
    "public_transport": {"en": "public transport", "fi": "joukkoliikenne", "sv": "kollektivtrafik"},
    "fuel": {"en": "fuel", "fi": "polttoaine", "sv": "bränsle"},
    "parking": {"en": "parking", "fi": "pysäköinti", "sv": "parkering"},
    "restaurants": {"en": "restaurant", "fi": "ravintola", "sv": "restauranger"},
    "fast_food_cafes": {"en": "café & fast food", "fi": "kahvila- ja pikaruoka", "sv": "kaféer och snabbmat"},
    "bars": {"en": "bar", "fi": "baari", "sv": "barer"},
    "supermarket": {"en": "supermarket", "fi": "supermarket", "sv": "matbutiker"},
    "convenience_store": {"en": "kiosk", "fi": "kioski", "sv": "kiosker"},
    "pharmacy": {"en": "pharmacy", "fi": "apteekki", "sv": "apotek"},
    "doctor": {"en": "doctor", "fi": "lääkäri", "sv": "läkare"},
    "dentist": {"en": "dentist", "fi": "hammaslääkäri", "sv": "tandläkare"},
    "electronics": {"en": "electronics", "fi": "elektroniikka", "sv": "elektronik"},
    "furniture": {"en": "furniture", "fi": "huonekalu", "sv": "möbler"},
    "hardware_diy": {"en": "DIY", "fi": "rautakauppa", "sv": "järnhandel"},
    "cinema": {"en": "cinema", "fi": "elokuva", "sv": "bio"},
    "concerts_events": {"en": "concert & event", "fi": "tapahtuma", "sv": "konserter och evenemang"},
    "recreation": {"en": "recreation", "fi": "vapaa-aika", "sv": "fritid"},
    "clothing": {"en": "clothing", "fi": "vaate", "sv": "kläder"},
    "sports_gear": {"en": "sports gear", "fi": "urheiluväline", "sv": "sportutrustning"},
    "books_hobbies": {"en": "books & hobbies", "fi": "kirja- ja harrastus", "sv": "böcker och hobbyer"},
    "flights": {"en": "flight", "fi": "lento", "sv": "flyg"},
    "hotels": {"en": "hotel", "fi": "hotelli", "sv": "hotell"},
    "car_rental": {"en": "car rental", "fi": "autonvuokraus", "sv": "biluthyrning"},
}
BASKET_LABEL: dict[str, dict[str, str]] = {
    "fixed": {"en": "fixed essentials", "fi": "kiinteät välttämättömät", "sv": "fasta måsten"},
    "irregular": {"en": "irregular essentials", "fi": "epäsäännölliset välttämättömät", "sv": "oregelbundna måsten"},
    "leak": {"en": "everyday leaks", "fi": "arjen vuodot", "sv": "vardagsläckor"},
    "income": {"en": "income", "fi": "tulot", "sv": "inkomster"},
    "saving": {"en": "saving", "fi": "säästäminen", "sv": "sparande"},
}

#: Finnish names + one-line descriptions for the spender archetypes (SPEC §3.1 profile).
ARCHETYPE_FI: dict[str, tuple[str, str]] = {
    "steady_planner": ("Suunnitelmallinen", "Kulutuksesi on tasaista ja ennakoitavaa, ja rahaa jää säästöön."),
    "weekend_treater": ("Viikonloppuherkuttelija", "Arki sujuu tiukasti, mutta viikonloppuisin raha liikkuu."),
    "latte_leaker": ("Lattevuotaja", "Paljon pieniä arjen ostoksia, jotka kertyvät hiljaa isoksi summaksi."),
    "impulse_splurger": ("Heräteostelija", "Välillä tulee isompia, suunnittelemattomia ostoksia."),
    "squirrel_saver": ("Oravasäästäjä", "Pistät rahaa sivuun ahkerasti ja kulutat harkiten."),
    "tightrope_walker": ("Nuorallatanssija", "Saldo käy usein lähellä nollaa, joten pienikin yllätys tuntuu."),
}

#: Swedish names + one-line descriptions for the same archetypes.
ARCHETYPE_SV: dict[str, tuple[str, str]] = {
    "steady_planner": ("Den stadiga planeraren", "Dina utgifter är jämna och förutsägbara, och det blir pengar över till sparande."),
    "weekend_treater": ("Helgnjutaren", "Vardagen sköter du stramt, men på helgerna rullar pengarna."),
    "latte_leaker": ("Latteläckaren", "Många små vardagsköp som i det tysta växer till en stor summa."),
    "impulse_splurger": ("Impulsköparen", "Då och då blir det större köp som inte var planerade."),
    "squirrel_saver": ("Ekorrspararen", "Du lägger flitigt undan pengar och handlar med eftertanke."),
    "tightrope_walker": ("Lindansaren", "Saldot är ofta nära noll, så även en liten överraskning känns."),
}
ARCHETYPE_L10N: dict[str, dict[str, tuple[str, str]]] = {"fi": ARCHETYPE_FI, "sv": ARCHETYPE_SV}


PERIODS: tuple[str, ...] = (
    "this_week",
    "last_week",
    "this_month",
    "last_month",
    "last_30_days",
    "last_3_months",
    "last_6_months",
    "last_12_months",
    "this_year",
    "last_year",
    "all",
)

MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_FI = ("tammi", "helmi", "maalis", "huhti", "touko", "kesä", "heinä", "elo", "syys", "loka", "marras", "joulu")
MONTHS_SV = ("jan", "feb", "mars", "apr", "maj", "juni", "juli", "aug", "sep", "okt", "nov", "dec")
MONTHS_FULL_EN = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December")


def _month_start(d: date) -> date:
    return d.replace(day=1)


def add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    # clamp day
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, 28)


def resolve_period(period: str | None, as_of: date) -> tuple[date | None, date | None]:
    """Map a named period to inclusive ``(start, end)`` dates relative to ``as_of``."""
    p = (period or "").strip().lower()
    if p == "this_week":
        return as_of - timedelta(days=as_of.weekday()), as_of
    if p == "last_week":
        this_monday = as_of - timedelta(days=as_of.weekday())
        return this_monday - timedelta(days=7), this_monday - timedelta(days=1)
    if p == "this_month":
        return _month_start(as_of), as_of
    if p == "last_month":
        first_this = _month_start(as_of)
        last_prev = first_this - timedelta(days=1)
        return _month_start(last_prev), last_prev
    if p == "last_30_days":
        return as_of - timedelta(days=29), as_of
    if p == "last_3_months":
        return add_months(as_of, -3) + timedelta(days=1), as_of
    if p == "last_6_months":
        return add_months(as_of, -6) + timedelta(days=1), as_of
    if p == "last_12_months":
        return add_months(as_of, -12) + timedelta(days=1), as_of
    if p == "this_year":
        return date(as_of.year, 1, 1), as_of
    if p == "last_year":
        return date(as_of.year - 1, 1, 1), date(as_of.year - 1, 12, 31)
    return None, None


def parse_iso(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}", text):
            return date.fromisoformat(text + "-01")
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def format_period(start: object, end: object, locale: str = "en") -> str:
    """Human period label: ``Sep 2026`` / ``Jun–Sep 2026`` / ``syyskuu 2026`` / ``sep 2026``."""
    s, e = parse_iso(start), parse_iso(end)
    names = {"fi": MONTHS_FI, "sv": MONTHS_SV}.get(locale, MONTHS_EN)
    suffix = "kuu" if locale == "fi" else ""
    if not s and not e:
        return {"fi": "kaikki tapahtumat", "sv": "alla transaktioner"}.get(locale, "all history")
    s = s or e
    e = e or s
    assert s is not None and e is not None
    if (s.year, s.month) == (e.year, e.month):
        if (e - s).days <= 7 and not (s.day == 1 and e.day >= 28):
            if locale in ("fi", "sv"):
                return f"{s.day}.–{e.day}.{e.month}.{e.year}"
            return f"{s.day}–{e.day} {names[e.month - 1]} {e.year}"
        return f"{names[s.month - 1]}{suffix} {s.year}"
    if s.year == e.year:
        return f"{names[s.month - 1]}–{names[e.month - 1]}{suffix} {e.year}"
    return f"{names[s.month - 1]}{suffix} {s.year}–{names[e.month - 1]}{suffix} {e.year}"


def normalize_category(value: object) -> str | None:
    """Map free text ("dining out", "ravintolat", "restaurants") to a canonical category."""
    if not value:
        return None
    text = str(value).strip()
    for cat in ALL_CATEGORIES:
        if text.lower() == cat.lower():
            return cat
    for table in (CATEGORY_FI, CATEGORY_SV):
        for cat, label in table.items():
            if text.lower() == label:
                return cat
    match = match_vocabulary(text)
    if match and match[0] == "category":
        return match[1]
    if match and match[0] == "subcategory":
        return SUBCATEGORIES[match[1]][0]
    return None


def match_vocabulary(text: str) -> tuple[str, str] | None:
    """Return the first (kind, value) synonym hit in ``text``."""
    low = text.lower()
    for pattern, hit in SYNONYMS:
        if re.search(pattern, low):
            return hit
    return None


def fmt_eur(value: float | int | None, locale: str = "en", decimals: int | None = None) -> str:
    """Format money for chat text: ``1,234.50 €`` (en) / ``1 234,50 €`` (fi, sv)."""
    if value is None:
        return "–"
    v = float(value)
    if decimals is None:
        decimals = 0 if abs(v) >= 100 else 2
    text = f"{v:,.{decimals}f}"
    if locale in ("fi", "sv"):
        text = text.replace(",", " ").replace(".", ",")
    return f"{text} €"


def fi_inessive_period(label: str) -> str:
    """'elokuu 2026' → 'elokuussa 2026'; other labels → 'ajalla <label>'."""
    import re as _re

    m = _re.fullmatch(r"(\w+kuu) (\d{4})", label)
    if m:
        return f"{m.group(1)}ssa {m.group(2)}"
    return f"ajalla {label}"


def fi_cost_stem(category: str | None = None, subcategory: str | None = None, basket: str | None = None) -> str:
    """Finnish compound stem for '<stem>kulut' phrases (taksikulut, ravintolakulut…)."""
    if subcategory and subcategory in SUBCATEGORY_LABEL:
        return SUBCATEGORY_LABEL[subcategory]["fi"]
    if category and category in CATEGORY_FI_STEM:
        return CATEGORY_FI_STEM[category]
    if basket:
        return {"leak": "vuoto", "fixed": "kiinteät ", "irregular": "epäsäännölliset "}.get(basket, "")
    return ""


def category_label(category: str | None, locale: str = "en") -> str:
    if not category:
        return ""
    if locale == "fi":
        return CATEGORY_FI.get(category, category.lower())
    if locale == "sv":
        return CATEGORY_SV.get(category, category.lower())
    return category.lower()
