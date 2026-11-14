"""Persona registry: Sisu (The Trainer) and Aava (The Mentor).

Both are *human* cartoon characters (SPEC §6b): Sisu is a Finnish man in his late
twenties — sandy hair, short beard, glasses, amber quarter-zip, smartwatch — and Aava
is a woman in her mid-thirties with a pencil in her hair bun, round tortoiseshell
glasses, a teal cardigan and a notebook. Friendly *and* intellectual: they are coaches
you would trust with a spreadsheet, not mascots.

Why two characters with the same tools?
Financial-literacy research is clear that one teaching style does not fit everyone.
Some people respond to energy, challenges and streaks (behavioural "commitment
devices"); others need the *why* explained calmly before they change a habit. Both
characters share exactly the same data tools and safety rules, so their numbers are
identical — only the pedagogy differs:

* **Sisu** teaches by doing: turns insights into one concrete challenge ("reps").
* **Aava** teaches by understanding: explains the mechanism, then asks one reflective
  question (Socratic method).

All persona content (voice rules, example phrasing in en/fi/sv, greetings, starter chips,
TTS voice parameters, colours) lives in ``app/data/personas.json`` so designers and
content people can tune it without touching Python, and so the mobile app can render
the same metadata via ``GET /api/personas``.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from app.agent.lang import LOCALES, norm_locale
from app.agent.settings import APP_DATA_DIR

PERSONAS_PATH = APP_DATA_DIR / "personas.json"
SUPPORTED_LOCALES = LOCALES
_YOU = {"en": "there", "fi": "sinä", "sv": "du"}


@dataclass(frozen=True)
class Persona:
    """Typed view over one entry in ``personas.json``."""

    id: str
    name: str
    emoji: str
    color: str
    raw: dict[str, Any]

    def text(self, path: str, locale: str, default: str = "") -> str:
        """Fetch a localised string via a dotted path, e.g. ``status.thinking``."""
        node: Any = self.raw
        for part in path.split("."):
            if not isinstance(node, dict):
                return default
            node = node.get(part)
        if isinstance(node, dict):
            return str(node.get(norm_locale(locale)) or node.get("en") or default)
        return str(node) if node is not None else default

    def fallback_phrase(self, key: str, locale: str) -> str:
        block = (self.raw.get("fallback") or {}).get(norm_locale(locale)) or (
            self.raw.get("fallback") or {}
        ).get("en", {})
        value = block.get(key, "")
        if isinstance(value, list):
            return random.choice(value) if value else ""
        return str(value)

    def greeting(self, locale: str, name: str = "") -> str:
        loc = norm_locale(locale)
        greetings = self.raw.get("greeting") or {}
        lines = greetings.get(loc) or greetings.get("en") or []
        line = random.choice(lines) if lines else f"Hi {{name}}, I'm {self.name}!"
        return line.replace("{name}", name or _YOU[loc])

    def suggestions(self, locale: str) -> list[str]:
        chips = self.raw.get("suggestions") or {}
        return list(chips.get(norm_locale(locale)) or chips.get("en") or [])

    def system_prompt_block(self, locale: str) -> str:
        """Render the persona section of the system prompt.

        Voice and pedagogy rules are written in English (the model follows English
        instructions most reliably); example phrasing is given in the user's locale so
        the model mirrors the right register in Finnish and Swedish too.
        """
        p = self.raw.get("prompt") or {}
        loc = norm_locale(locale)
        examples = (p.get("example_phrases") or {}).get(loc) or (p.get("example_phrases") or {}).get(
            "en", []
        )
        lines = [p.get("identity", f"You are {self.name}.")]
        if p.get("voice"):
            lines.append("VOICE:\n" + "\n".join(f"- {v}" for v in p["voice"]))
        if p.get("pedagogy"):
            lines.append("PEDAGOGY:\n" + "\n".join(f"- {v}" for v in p["pedagogy"]))
        if examples:
            lines.append(
                "EXAMPLE PHRASING (style only — the numbers in these examples are NOT the user's):\n"
                + "\n".join(f"- {e}" for e in examples)
            )
        if p.get("closing_style"):
            lines.append(f"CLOSING: {p['closing_style']}")
        return "\n\n".join(lines)


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    with PERSONAS_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=8)
def get_persona(persona_id: str | None) -> Persona:
    """Return the persona by id, falling back to the default (Sisu) for unknown ids."""
    data = _load()
    items = {p["id"]: p for p in data.get("personas", [])}
    key = (persona_id or "").lower()
    raw = items.get(key) or items.get(data.get("default", "sisu")) or next(iter(items.values()))
    return Persona(id=raw["id"], name=raw["name"], emoji=raw["emoji"], color=raw["color"], raw=raw)


def list_personas() -> list[dict[str, Any]]:
    """Public persona metadata (no prompt internals) — handy for API consumers."""
    public_keys = ("id", "name", "emoji", "title", "tagline", "appearance", "color", "accent", "voice", "greeting", "suggestions", "pedagogy")
    return [{k: p[k] for k in public_keys if k in p} for p in _load().get("personas", [])]
