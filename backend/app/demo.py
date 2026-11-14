"""Demo customers shown in the app's persona picker (SPEC §1.1).

The display names are *fictional labels* chosen to tell six different money stories with
the synthetic dataset; age and postal code always come from the data itself. Any other
``customer_id`` in the dataset works through the API as well.
"""

from __future__ import annotations

from typing import Any

#: customer_id → presentation metadata (name/tagline/avatar are demo labels only).
DEMO_CUSTOMERS: dict[str, dict[str, Any]] = {
    "CUST05020": {"name": "Emma", "tagline": "Irregular income, leaky everyday spending",
                  "avatar_emoji": "🎧", "story": "young adult money literacy"},
    "CUST00584": {"name": "Leo", "tagline": "Salary lasts… almost. Dips below zero",
                  "avatar_emoji": "🛹", "story": "survive the month"},
    "CUST00586": {"name": "Mika", "tagline": "High income, big leaks, wants to invest",
                  "avatar_emoji": "🚴", "story": "invest & goals"},
    "CUST00961": {"name": "Sanna", "tagline": "Mortgage was rejected, wants a home",
                  "avatar_emoji": "🏡", "story": "home readiness"},
    "CUST00001": {"name": "Pirjo", "tagline": "Steady saver, how do I compare?",
                  "avatar_emoji": "🌻", "story": "benchmarks"},
    "CUST05014": {"name": "Joni",
                  "tagline": "An unexpected repair led to a payday loan. "
                             "Now aiming to get back in the black.",
                  "avatar_emoji": "🧰", "story": "get back in the black"},
}


#: Taglines in fi / sv (the English ones live in :data:`DEMO_CUSTOMERS`).
TAGLINES_L10N: dict[str, tuple[str, str]] = {
    "CUST05020": ("Epäsäännölliset tulot, arjen kulut vuotavat", "Oregelbunden inkomst, vardagsutgifterna läcker"),
    "CUST00584": ("Palkka riittää… melkein. Saldo käy miinuksella", "Lönen räcker… nästan. Saldot går på minus"),
    "CUST00586": ("Hyvät tulot, isot vuodot, haluaa sijoittaa", "Hög inkomst, stora läckor, vill placera"),
    "CUST00961": ("Asuntolaina hylättiin, haaveena oma koti", "Bostadslånet fick avslag, drömmer om ett eget hem"),
    "CUST00001": ("Tasainen säästäjä – miten vertaudun muihin?", "Stadig sparare – hur står jag mig mot andra?"),
    "CUST05014": ("Yllättävä remontti johti pikavippiin. Nyt tavoitteena on päästä takaisin plussalle.",
                   "En oväntad reparation ledde till ett snabblån. Nu är målet att komma tillbaka på plus."),
}


def tagline(customer_id: str) -> str:
    """Demo tagline in the current request locale."""
    from app.i18n import tr

    meta = DEMO_CUSTOMERS.get(customer_id, {})
    pair = TAGLINES_L10N.get(customer_id)
    en = str(meta.get("tagline", ""))
    return tr(en, pair[0], pair[1]) if pair else en


def display_name(customer_id: str) -> str:
    """Friendly name for a customer: demo label, else a neutral 'Customer 1234'."""
    from app.i18n import tr

    meta = DEMO_CUSTOMERS.get(customer_id)
    if meta:
        return str(meta["name"])
    digits = customer_id.removeprefix("CUST").lstrip("0") or "0"
    return tr(f"Customer {digits}", f"Asiakas {digits}", f"Kund {digits}")
