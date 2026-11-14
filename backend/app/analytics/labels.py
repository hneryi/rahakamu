"""Human-friendly, brand-free labels and icons for merchants, MCCs and categories.

Why
---
The dataset only has opaque merchant ids (``MRC-RES-0038``) and ISO 18245 merchant
category codes (MCC). Users need something readable, but we must **never invent or leak
real brand names**. So a merchant is shown as *"<generic MCC label> #<merchant number>"*,
e.g. ``MRC-RES-0038`` + MCC 5814 → ``"Café #38"``. That is stable (same merchant, same
label), privacy-safe, and still lets a user notice "I go to Café #38 a lot".

Labels come from ``app/data/mcc.json`` when that file exists (it is curated by the
content builder and is localised en / fi / sv); otherwise the built-in :data:`MCC_BUILTIN`
map is used. The JSON loader is deliberately defensive about the file's shape. Labels follow
the current request locale (:mod:`app.i18n`).
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from app import i18n
from app.config import APP_DATA_DIR

log = logging.getLogger(__name__)

#: mcc → (long label, short merchant noun, emoji). Covers every MCC present in the data.
MCC_BUILTIN: dict[int, tuple[str, str, str]] = {
    5411: ("Grocery store / supermarket", "Grocery store", "🛒"),
    5499: ("Convenience store / kiosk", "Kiosk", "🏪"),
    5422: ("Butcher / meat shop", "Butcher", "🥩"),
    5451: ("Dairy shop", "Dairy shop", "🧀"),
    5812: ("Restaurant", "Restaurant", "🍽️"),
    5814: ("Fast food & café", "Café", "☕"),
    5813: ("Bar / nightlife", "Bar", "🍸"),
    5542: ("Fuel (automated pump)", "Fuel station", "⛽"),
    5541: ("Service station", "Service station", "⛽"),
    7523: ("Parking", "Parking", "🅿️"),
    4111: ("Public transport", "Public transport", "🚌"),
    4121: ("Taxi / ride-hailing", "Taxi", "🚕"),
    7922: ("Theatre & concerts", "Concert venue", "🎭"),
    7999: ("Recreation services", "Recreation", "🎳"),
    7832: ("Cinema", "Cinema", "🎬"),
    7991: ("Attractions & tours", "Attraction", "🎡"),
    7996: ("Amusement park", "Amusement park", "🎢"),
    5912: ("Pharmacy", "Pharmacy", "💊"),
    8011: ("Doctor", "Clinic", "🩺"),
    8099: ("Health services", "Health service", "🏥"),
    8021: ("Dentist", "Dentist", "🦷"),
    5200: ("Home supply / DIY", "Home supply store", "🔨"),
    5732: ("Electronics", "Electronics store", "💻"),
    5251: ("Hardware store", "Hardware store", "🛠️"),
    5712: ("Furniture", "Furniture store", "🛋️"),
    5734: ("Software & apps", "Software store", "💾"),
    5941: ("Sporting goods", "Sports store", "⚽"),
    5651: ("Clothing", "Clothing store", "👕"),
    5999: ("Specialty retail", "Shop", "🛍️"),
    5691: ("Fashion", "Fashion store", "👗"),
    5942: ("Books", "Bookstore", "📚"),
    5945: ("Toys & hobbies", "Hobby store", "🧸"),
    4722: ("Travel agency", "Travel agency", "🧳"),
    4511: ("Airline", "Airline", "✈️"),
    7011: ("Hotel", "Hotel", "🏨"),
    7512: ("Car rental", "Car rental", "🚗"),
}

#: category → (label used when no merchant/MCC is known, emoji)
CATEGORY_DEFAULTS: dict[str, tuple[str, str]] = {
    "Groceries": ("Groceries", "🛒"),
    "Restaurants": ("Eating out", "🍽️"),
    "Transportation": ("Transport", "🚌"),
    "Utilities": ("Utility bill", "💡"),
    "Entertainment": ("Entertainment", "🎟️"),
    "Health": ("Health", "🩺"),
    "Salary": ("Salary", "💶"),
    "Home & Tech": ("Home & tech", "🏠"),
    "Housing": ("Rent / housing", "🏠"),
    "Lifestyle": ("Lifestyle shopping", "🛍️"),
    "Travel": ("Travel", "✈️"),
    "Invest Deposit": ("Investment deposit", "📈"),
    "Other Income": ("Other income", "💰"),
    "Salary Sweep": ("Transfer to savings", "🐷"),
    "Invest Withdraw": ("Investment withdrawal", "📉"),
}

#: merchant id prefix → generic noun when the MCC is missing
_PREFIX_NOUN: dict[str, str] = {
    "GRO": "Grocery store",
    "RES": "Restaurant",
    "TRN": "Transport",
    "ENT": "Entertainment venue",
    "HEA": "Health service",
    "HMT": "Home & tech store",
    "LIF": "Shop",
    "TRV": "Travel service",
}

_MERCHANT_RE = re.compile(r"^MRC-([A-Z]+)-0*(\d+)$")


def _first_str(d: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


#: Built-in fi/sv fallbacks for category labels (mcc.json ``null_mcc`` wins when present).
_CATEGORY_L10N: dict[str, dict[str, str]] = {
    "fi": {"Groceries": "Ruokaostokset", "Restaurants": "Ulkona syöminen", "Transportation": "Liikkuminen",
           "Utilities": "Asumisen lasku", "Entertainment": "Viihde", "Health": "Terveys", "Salary": "Palkka",
           "Home & Tech": "Koti ja tekniikka", "Housing": "Vuokra / asuminen", "Lifestyle": "Ostokset",
           "Travel": "Matkailu", "Invest Deposit": "Sijoitustalletus", "Other Income": "Muut tulot",
           "Salary Sweep": "Siirto säästöön", "Invest Withdraw": "Sijoitusten nosto"},
    "sv": {"Groceries": "Matinköp", "Restaurants": "Äta ute", "Transportation": "Transport",
           "Utilities": "Boenderäkning", "Entertainment": "Nöjen", "Health": "Hälsa", "Salary": "Lön",
           "Home & Tech": "Hem och teknik", "Housing": "Hyra / boende", "Lifestyle": "Shopping",
           "Travel": "Resor", "Invest Deposit": "Insättning till placeringar", "Other Income": "Övriga inkomster",
           "Salary Sweep": "Överföring till sparande", "Invest Withdraw": "Uttag från placeringar"},
}
_PREFIX_NOUN_L10N: dict[str, dict[str, str]] = {
    "fi": {"GRO": "Ruokakauppa", "RES": "Ravintola", "TRN": "Liikenne", "ENT": "Viihdepaikka",
           "HEA": "Terveyspalvelu", "HMT": "Koti- ja tekniikkaliike", "LIF": "Liike", "TRV": "Matkapalvelu"},
    "sv": {"GRO": "Matbutik", "RES": "Restaurang", "TRN": "Trafik", "ENT": "Nöjesställe",
           "HEA": "Hälsotjänst", "HMT": "Hem- och teknikbutik", "LIF": "Butik", "TRV": "Resetjänst"},
}

_MccEntry = tuple[dict[str, str], dict[str, str], str | None]


def _texts(val: dict[str, Any], dict_key: str, flat_prefix: str, flat_alts: tuple[str, ...]) -> dict[str, str]:
    """Collect ``{locale: text}`` from ``{"label": {"en":..}}`` and ``short_label_en``-style keys."""
    out: dict[str, str] = {}
    nested = val.get(dict_key)
    if isinstance(nested, dict):
        out.update({k: v.strip() for k, v in nested.items() if isinstance(v, str) and v.strip()})
    elif isinstance(nested, str) and nested.strip():
        out["en"] = nested.strip()
    for code in ("en", "fi", "sv"):
        flat = val.get(f"{flat_prefix}_{code}")
        if isinstance(flat, str) and flat.strip():
            out[code] = flat.strip()
    if "en" not in out:
        alt = _first_str(val, flat_alts)
        if alt:
            out["en"] = alt
    return out


def _load_mcc_json() -> dict[str, Any]:
    path = APP_DATA_DIR / "mcc.json"
    if not path.exists():
        return {}
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("mcc.json unreadable (%s); using built-in labels", exc)
        return {}
    return raw if isinstance(raw, dict) else {"codes": raw}


@lru_cache(maxsize=1)
def _json_mcc() -> dict[int, _MccEntry]:
    """Parse ``app/data/mcc.json`` whatever its exact shape: ``{mcc: str}``,
    ``{mcc: {label, short, icon}}``, ``[{mcc, label, ...}]`` or wrapped in a top-level key.
    Returns mcc → ({locale: label}, {locale: short label}, icon)."""
    raw: Any = _load_mcc_json()
    if isinstance(raw, dict):
        for wrapper in ("mcc", "mccs", "codes", "items", "labels", "data"):
            if wrapper in raw and isinstance(raw[wrapper], dict | list):
                raw = raw[wrapper]
                break
    entries: list[tuple[Any, Any]] = []
    if isinstance(raw, dict):
        entries = list(raw.items())
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                code = item.get("mcc", item.get("code", item.get("mcc_code")))
                entries.append((code, item))
    out: dict[int, _MccEntry] = {}
    for code, val in entries:
        try:
            mcc = int(str(code))
        except (TypeError, ValueError):
            continue
        if isinstance(val, str):
            out[mcc] = ({"en": val}, {}, None)
        elif isinstance(val, dict):
            labels = _texts(val, "label", "label", ("name", "en", "description", "title"))
            shorts = _texts(val, "short_label", "short_label", ("short", "merchant_label", "merchant_noun", "noun"))
            out[mcc] = (labels, shorts, _first_str(val, ("icon", "emoji")))
    return out


@lru_cache(maxsize=1)
def _json_categories() -> dict[str, dict[str, str]]:
    """category → {locale: display name} from mcc.json ``categories``."""
    raw = _load_mcc_json().get("categories")
    if not isinstance(raw, dict):
        return {}
    return {cat: _texts(val, "label", "label", ()) for cat, val in raw.items() if isinstance(val, dict)}


def _in_locale(texts: dict[str, str]) -> str | None:
    return texts.get(i18n.loc()) or texts.get("en")


def category_default_label(category: str | None) -> str:
    """Label for a row without merchant/MCC (``"Utility bill"``), in the current locale."""
    cat = category or ""
    current = i18n.loc()
    if current != "en":
        hit = _CATEGORY_L10N[current].get(cat)
        if hit:
            return hit
    return CATEGORY_DEFAULTS.get(cat, (cat or i18n.tr("Transaction", "Tapahtuma", "Transaktion"), ""))[0]


def category_label_l10n(category: str | None) -> str:
    """Display name of a dataset category in the current locale (mcc.json first)."""
    if not category:
        return ""
    js = _json_categories().get(category)
    if js and i18n.loc() in js:
        return js[i18n.loc()]
    return category_default_label(category)


def mcc_label(mcc: int | None) -> str | None:
    """Readable MCC description in the current locale (``None`` when MCC is missing)."""
    if mcc is None:
        return None
    mcc = int(mcc)
    js = _json_mcc().get(mcc)
    if js:
        text = _in_locale(js[0])
        if text:
            return text
    b = MCC_BUILTIN.get(mcc)
    if b and i18n.loc() == "en":
        return b[0]
    return i18n.tr(f"Merchant category {mcc}", f"Toimialakoodi {mcc}", f"Branschkod {mcc}") if not b else b[0]


def _mcc_short(mcc: int) -> str | None:
    js = _json_mcc().get(mcc)
    if js:
        text = _in_locale(js[1])
        if text:
            return text
    b = MCC_BUILTIN.get(mcc)
    if b and i18n.loc() == "en":
        return b[1]
    if js:
        text = _in_locale(js[0])
        if text:
            return text
    return b[1] if b else None


def icon_for(category: str | None, mcc: int | None) -> str:
    """Emoji for a transaction row: MCC-specific first, then category default."""
    if mcc is not None:
        js = _json_mcc().get(int(mcc))
        if js and js[2]:
            return js[2]
        b = MCC_BUILTIN.get(int(mcc))
        if b:
            return b[2]
    return CATEGORY_DEFAULTS.get(category or "", ("", "💳"))[1]


def merchant_label(merchant_id: str | None, mcc: int | None, category: str | None) -> str:
    """Generic, brand-free merchant label, e.g. ``"Grocery store #35"`` (``"Matbutik #35"``).

    * merchant + MCC  → ``"<MCC short noun> #<n>"``
    * merchant only   → noun from the merchant-id prefix (``RES`` → Restaurant)
    * no merchant     → category default (``"Utility bill"``, ``"Salary"`` …)
    """
    if merchant_id:
        m = _MERCHANT_RE.match(merchant_id)
        num = m.group(2) if m else merchant_id[-4:].lstrip("0") or "0"
        noun = _mcc_short(int(mcc)) if mcc is not None else None
        if noun is None and m:
            prefix = m.group(1)
            current = i18n.loc()
            noun = (_PREFIX_NOUN_L10N[current].get(prefix) if current != "en" else None) or _PREFIX_NOUN.get(prefix)
        if noun is None and category:
            noun = category_default_label(category)
        return f"{noun or i18n.tr('Merchant', 'Kauppias', 'Handlare')} #{num}"
    return category_default_label(category)
