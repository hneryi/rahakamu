"""Last-line checks on a finished model answer (defence in depth behind the prompt).

The system prompt already forbids invented figures and investment picks, and the evals
measure how well the model obeys. A prompt is still only a request, so two cheap checks
run on every model-written answer before the ``done`` event:

1. **Unverified amounts.** The answer states euro amounts although *no data tool ran*
   this turn, and those amounts appear neither in the user-context block the model was
   given nor anywhere in the conversation. Sums/differences and arithmetic on user-supplied
   operands are allowed. Context-only unit conversions require a tool: multiplying a monthly
   surplus by 30 must not validate an invented rent.
2. **Investment picks.** A sentence that tells the user to buy or sell a *named* security
   (a ticker-like word next to "stock", "share", "osake", "aktie", "crypto"…) without a
   negation such as "I can't tell you which stock to buy".

What a check can do is limited by streaming: the text has already been shown, and SSE has
no "unsay" event. So a hit appends a short correction paragraph in the user's language,
sets the additive ``guardrail`` field of the ``done`` event and is logged. Both checks are
deliberately narrow; they are a safety net, not a replacement for the evals.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.evals.grounding import _close, allowed_values, extract_numbers
from app.agent.lang import pick

#: Smallest amount worth a correction; "a 5 € coffee" style examples are left alone.
MIN_AMOUNT = 50.0

_AMOUNT = re.compile(
    r"(?:€\s?(?P<pre>\d[\d \u00a0\u202f.,]*\d|\d))|(?:(?P<post>\d[\d \u00a0\u202f.,]*\d|\d)[ \u00a0\u202f]?(?:€|eur\b|euro\w*))",
    re.IGNORECASE,
)
_BUY_SELL = re.compile(
    r"\b(buy|buying|sell|selling|invest in|put (?:it|your money|everything) (?:in|into)"
    r"|osta|ostaa|ostamaan|myy|myydä|sijoita|sijoittaa"
    r"|köp|köpa|sälj|sälja|investera i)\b",
    re.IGNORECASE,
)
_INSTRUMENT = re.compile(
    r"\b(stocks?|shares?|equity|crypto\w*|coins?|tokens?|osake\w*|osakkei\w*|krypto\w*|aktie\w*)\b",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(can(?:'|’)?t|cannot|can not|won(?:'|’)?t|don(?:'|’)?t|do not|not|never|no specific|unable"
    r"|en|ei|emme|älä|enkä|voi suositella"
    r"|inte|aldrig|ingen|inga)\b",
    re.IGNORECASE,
)
_TICKER = re.compile(r"\b[A-ZÅÄÖ]{3,6}\b")
#: Upper-case words that are not securities.
_NOT_TICKERS = {"ETF", "ETFS", "EUR", "ASP", "USA", "OMX", "PEA", "VAT", "ALV", "MOMS", "FAQ", "AI", "TIP", "NOTE", "HUOM", "OBS"}


def _number(raw: str) -> float | None:
    """Parse ``1 234,50`` / ``1,234.50`` / ``999999.99`` leniently."""
    s = re.sub(r"[ \u00a0\u202f]", "", raw)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        head, _, tail = s.rpartition(",")
        s = head.replace(",", "") + ("." + tail if len(tail) != 3 else tail)
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.rsplit(".", 1)[1]) == 3):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def euro_amounts(text: str) -> list[float]:
    out: list[float] = []
    for m in _AMOUNT.finditer(text.replace("**", "")):
        value = _number(m.group("pre") or m.group("post") or "")
        if value is not None:
            out.append(value)
    return out


def unverified_amounts(answer: str, shown: list[Any], conversation: str) -> list[float]:
    """Euro amounts ≥ ``MIN_AMOUNT`` in ``answer`` that match nothing the model was shown."""
    amounts = [a for a in euro_amounts(answer) if abs(a) >= MIN_AMOUNT]
    if not amounts:
        return []
    allowed = allowed_values(shown, conversation, scale_conversions=False)
    # "12 000 € in 24 months is 500 € a month": products and quotients of what the user said
    said = sorted({abs(v) for v, _ in extract_numbers(conversation, "en") + extract_numbers(conversation, "fi") if v})[:40]
    for a in said:
        for b in said:
            allowed.add(a / b)
            allowed.add(a * b)
    return [a for a in amounts if not _close(a, allowed)]


def investment_pick(answer: str) -> str | None:
    """The offending sentence if the answer tells the user to buy / sell a named security."""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer):
        if not (_BUY_SELL.search(sentence) and _INSTRUMENT.search(sentence)):
            continue
        if _NEGATION.search(sentence):
            continue
        if any(t not in _NOT_TICKERS for t in _TICKER.findall(sentence)):
            return sentence.strip()
    return None


def review(answer: str, *, tools_ran: bool, shown: list[Any], conversation: str, locale: str) -> tuple[str | None, str]:
    """Return ``(code, correction_text)``; ``(None, "")`` when the answer is fine."""
    if investment_pick(answer):
        return "investment_pick", pick(
            locale,
            "One correction: I can't recommend buying or selling any specific investment. Please treat the above as general information, not advice. Investing always carries risk, and an S-Bank advisor can help you choose.",
            "Yksi korjaus: en voi suositella minkään yksittäisen sijoituskohteen ostamista tai myymistä. Pidä yllä olevaa yleisenä tietona, älä neuvona. Sijoittamiseen liittyy aina riski, ja S-Pankin neuvoja voi auttaa valinnassa.",
            "En rättelse: jag kan inte rekommendera att köpa eller sälja någon enskild placering. Se ovanstående som allmän information, inte som rådgivning. Att placera innebär alltid en risk, och en rådgivare på S-Banken kan hjälpa dig att välja.",
        )
    if not tools_ran and unverified_amounts(answer, shown, conversation):
        return "ungrounded_amount", pick(
            locale,
            "Please note: I did not look anything up in your account for this answer, so the amounts above are not verified figures from your own data. Ask me again and I will check them.",
            "Huomaa: en hakenut tähän vastaukseen mitään tilitiedoistasi, joten yllä olevat summat eivät ole tarkistettuja lukuja omista tiedoistasi. Kysy uudelleen, niin tarkistan ne.",
            "Observera: jag slog inte upp något i dina kontouppgifter för det här svaret, så beloppen ovan är inte kontrollerade siffror från dina egna uppgifter. Fråga igen så kontrollerar jag dem.",
        )
    return None, ""
