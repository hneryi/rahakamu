"""Grounding checker: does every number in an answer come from the data?

Why
---
The single worst failure of a money coach is a confident, wrong number. The prompt
forbids invented figures; this checker *verifies* it, so prompt changes can be
regression-tested (``evals/run.py``) instead of eyeballed.

Method
------
1. Extract numbers from the answer, locale-aware: ``3 899,71 €`` (fi, sv) and
   ``3,899.71 €`` (en), percentages, plain integers.
2. Build the *allowed* set from what the model was shown: every numeric value in the
   tool payloads (and the user-context block), numbers in the user's question, ISO-date
   parts, plus simple derived values a good answer may legitimately compute:
   ×100 / ÷100 (fractions ↔ percents), ×12 / ÷12 (month ↔ year), ×7 / ÷7 (day ↔ week),
   and pairwise sums / differences.
3. A number is grounded if it matches an allowed value within rounding tolerance
   (max(1 % relative, 0.6 absolute) — so 41.06 → "41 €" passes).
4. Small integers ≤ 12 (counts, "7-day challenge", "2 years") and years are exempt, as
   are round challenge percentages (5–50 % in steps of 5) which are behavioural targets,
   not claims about the user's data.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

_NUM_EN = re.compile(r"(?<![\w.])[-−]?\d{1,3}(?:(?:,\d{3})+|(?:[ \u00a0\u202f]\d{3})+)(?:\.\d+)?(?!\d)|(?<![\w.,])[-−]?\d+(?:\.\d+)?")
_NUM_FI = re.compile(r"(?<![\w,])[-−]?\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|(?<![\w,.])[-−]?\d+(?:,\d+)?")
_ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})(?:-(\d{2}))?\b")


@dataclass
class GroundingReport:
    numbers: list[float] = field(default_factory=list)
    ungrounded: list[float] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.ungrounded


def extract_numbers(text: str, locale: str = "en") -> list[tuple[float, bool]]:
    """Return ``(value, is_percent)`` pairs found in ``text``."""
    clean = re.sub(r"\*\*|__", "", text)
    out: list[tuple[float, bool]] = []
    # dates like 2026-09-30 / 30.9. / 30.9.2026 are not amounts: strip them first
    clean = _ISO_DATE.sub(" ", clean)
    clean = re.sub(r"\b\d{1,2}\.\d{1,2}\.(?:\d{4})?", " ", clean)
    clean = re.sub(r"\b\d{1,2}:\d{2}\b", " ", clean)
    comma_decimal = locale in ("fi", "sv")  # Finnish and Finland-Swedish: 1 234,50
    pattern = _NUM_FI if comma_decimal else _NUM_EN
    for m in pattern.finditer(clean):
        raw = m.group(0).replace("−", "-")
        if comma_decimal:
            raw = re.sub(r"[   ]", "", raw).replace(",", ".")
        else:
            raw = re.sub(r"[ ,\u00a0\u202f]", "", raw)
        try:
            value = float(raw)
        except ValueError:
            continue
        tail = clean[m.end() : m.end() + 12].lower()
        is_pct = bool(re.match(r"\s*(%|prosent|procent|percent)", tail))
        out.append((value, is_pct))
    return out


def _walk(obj: Any) -> Iterable[float]:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        yield float(obj)
    elif isinstance(obj, str):
        for m in _ISO_DATE.finditer(obj):
            for g in m.groups():
                if g:
                    yield float(g)
        # numbers inside curated text (lesson bodies, explanations), in either format
        for locale in ("en", "fi"):
            for value, _ in extract_numbers(obj, locale):
                yield value
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _walk(v)


def allowed_values(sources: list[Any], extra_text: str = "", *, scale_conversions: bool = True) -> set[float]:
    """Allow sums/differences; unitless scaling is optional for conservative no-tool checks."""
    base: set[float] = set()
    for src in sources:
        base.update(abs(v) for v in _walk(src))
    base.update(abs(v) for v, _ in extract_numbers(extra_text, "en"))
    base.update(abs(v) for v, _ in extract_numbers(extra_text, "fi"))
    derived = set(base)
    if scale_conversions:
        for v in base:
            derived.update({v * 100, v / 100, v * 12, v / 12, v * 7, v / 7, v / 30, v * 30})
    small = sorted(v for v in base if v >= 1)[:300]
    for i, a in enumerate(small):
        for b in small[i + 1 :]:
            derived.add(a + b)
            derived.add(abs(a - b))
    return derived


def _close(value: float, allowed: set[float]) -> bool:
    v = abs(value)
    tol = max(0.01 * v, 0.6)
    return any(abs(v - a) <= tol for a in allowed)


def check_grounding(answer: str, sources: list[Any], *, question: str = "", locale: str = "en") -> GroundingReport:
    """Check that numbers in ``answer`` are traceable to ``sources`` (+ question text)."""
    allowed = allowed_values(sources, question)
    report = GroundingReport()
    for value, is_pct in extract_numbers(answer, locale):
        report.numbers.append(value)
        v = abs(value)
        if v <= 12 and float(v).is_integer():
            continue
        if 2020 <= v <= 2040 and float(v).is_integer():
            continue
        if is_pct and 5 <= v <= 50 and v % 5 == 0:
            continue
        if not _close(v, allowed):
            report.ungrounded.append(value)
    return report
