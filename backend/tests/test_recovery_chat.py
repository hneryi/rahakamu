"""Exercise the real offline runner, not just individual response templates."""
import json

import pytest

from app.agent import fallback
from app.agent.events import ChatRequest, token
from app.agent.orchestrator import run_chat
from app.analytics import nudges, recovery
from app.i18n import use_locale

QUESTIONS = {
    "en": ["How do I get back to a positive balance?", "Where does the six-month spending gap come from?", "What is safe to spend this week?", "Show my goals", "How much would I save if I reduced dining out by 20%?", "How do I make it to payday?"],
    "fi": ["Miten pääsen takaisin plussalle?", "Mistä kuuden kuukauden menoero muodostuu?", "Paljonko voin käyttää tällä viikolla?", "Näytä tavoitteet", "Paljonko säästäisin, jos vähentäisin ulkona syömistä 20%?", "Miten selviän palkkapäivään asti?"],
    "sv": ["Hur kommer jag tillbaka till plus?", "Var kommer utgiftsgapet på sex månader från?", "Hur mycket kan jag tryggt använda den här veckan?", "Visa mina mål", "Hur mycket skulle jag spara om jag åt ute 20% mindre?", "Hur klarar jag mig till lönedagen?"],
}
TOOLS = ["get_overview", "query_spending", "safe_to_spend", "list_goals", "simulate_what_if", "survival_plan"]


@pytest.mark.parametrize("persona", ["sisu", "aava"])
@pytest.mark.parametrize("locale", ["en", "fi", "sv"])
async def test_real_offline_recovery_routes(monkeypatch, persona, locale):
    async def instant(text, delay=0):
        yield token(text)
    monkeypatch.setattr(fallback, "stream_text", instant)
    for question, tool in zip(QUESTIONS[locale], TOOLS):
        trace = {}
        req = ChatRequest(customer_id="CUST05014", persona=persona, locale=locale,
                          messages=[{"role": "user", "content": question}])
        events = [e async for e in run_chat(req, force_offline=True, trace=trace)]
        assert trace["results"][0][0] == tool
        text = " ".join(e.data["text"] for e in events if e.event == "token")
        done = events[-1].data
        combined = text + " ".join(done["suggestions"])
        assert not any(s in combined.lower() for s in ["streak", "putki", "sviten", "siirrä säästö tavoitteeseen", "add something to one goal", "lisää jotain yhteen", "flytta det sparade", "invested it", "sijoittaisin", "ajasta kuukausisiirto"]), combined
        assert done["mood"] == "concerned"
        if tool == "query_spending":
            result = trace["results"][0][1]
            assert result.raw["period"]["start"] == "2026-03-01"
            assert result.raw["period"]["end"] == "2026-08-31"
            assert str(result.sources["start"]) == "2026-03-01"
            assert str(result.sources["end"]) == "2026-08-31"
            assert any(word in text.lower() for word in ("income", "tulot", "inkomster"))
        if tool == "simulate_what_if":
            assert any(word in text.lower() for word in ("closing the gap", "vajetta umpeen", "täppa till"))


def test_bills_total_excludes_savings():
    with use_locale("en"):
        nudge = nudges._bills_nudge({"upcoming_bills_total": 9999}, [{"amount": 17}])
    assert "17" in nudge["text"] and "9,999" not in nudge["text"]
    assert "which are essential" in nudge["text"]


@pytest.mark.parametrize("balance", [-1, 0, 1])
@pytest.mark.parametrize("surplus", [-1, 0, 1])
def test_all_sign_combinations(balance, surplus):
    expected = "balance_repair" if balance < 0 else "cashflow_stabilizing" if surplus < 0 else "ordinary"
    assert recovery.classify(balance, surplus) == expected


def test_unknown_answer_is_neutral():
    from app.agent.personas import get_persona
    from app.agent.tools import ToolResult
    result = ToolResult(llm_payload={}, raw={"status": "comfortable", "safe_per_day": 0})
    text = fallback.compose_answer([("safe_to_spend", result)], get_persona("sisu"), "fi", recovery_context={"state": "unknown"})
    assert "ei ole riittävästi" in text and "0" not in text
    json.dumps({"answer": text}, allow_nan=False)
