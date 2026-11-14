"""Trilingual backend (en / fi / sv, SPEC §5.6) and human coach personas (SPEC §6b).

Covers the language detector, ``?locale=`` on the REST routes (no English leaking into
fi / sv payloads), the Swedish offline router and templates, the turn-language rule
("answer in the language the user wrote in") and the absence of animal wording.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import pytest

from app.agent.events import ChatRequest
from app.agent.lang import detect_language, norm_locale
from tests.conftest import DEMO_IDS

AS_OF = date(2026, 9, 18)
ANIMAL = re.compile(r"\b(bears?|owls?|karhu\w*|pöllö\w*|björn\w*|ugglan?|paws?|tassu\w*|feathers?|hoot\w*|growl\w*)\b|🐻|🦉", re.I)


# ----------------------------------------------------------------------------- detector


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("How much did I spend on taxis last month?", "en"),
        ("What is safe for me to spend this week?", "en"),
        ("Paljonko käytin takseihin viime kuussa?", "fi"),
        ("Miten selviän tästä kuusta 300 eurolla?", "fi"),
        ("Hur mycket lade jag på taxi förra månaden?", "sv"),
        ("hjälp mig spara till en bil som kostar 12 000 €", "sv"),
        ("hur klarar jag månaden med 150 euro", "sv"),
        ("var läcker mina pengar", "sv"),
        ("ja, skapa målet", "sv"),
        ("Hurdan konsument är jag?", "sv"),
    ],
)
def test_detect_language(text: str, expected: str) -> None:
    assert detect_language(text, "en") == expected
    # the app locale must not override clear evidence
    assert detect_language(text, "fi" if expected != "fi" else "sv") == expected


@pytest.mark.parametrize("text", ["ok", "300 €", "👍", "", "Taxi?"])
def test_detect_language_falls_back_to_locale_when_unsure(text: str) -> None:
    for loc in ("en", "fi", "sv"):
        assert detect_language(text, loc) == loc


def test_norm_locale() -> None:
    assert [norm_locale(x) for x in ("sv-FI", "FI", None, "de", "", "en_GB", "x" * 300)] == ["sv", "fi", "en", "en", "en", "en", "en"]


# ----------------------------------------------------------------------------- REST


def _sentences(obj: Any, skip: tuple[str, ...] = ("note", "url", "name")) -> list[str]:
    """Human sentences (≥ 4 words) anywhere in a JSON payload."""
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in skip:
                out += _sentences(v, skip)
    elif isinstance(obj, list):
        for v in obj:
            out += _sentences(v, skip)
    elif isinstance(obj, str) and " " in obj and len(re.findall(r"[^\W\d_]{2,}", obj)) >= 4:
        out.append(obj)
    return out


ROUTES = ["overview", "baskets", "safe-to-spend", "profile", "nudges", "survival", "recurring", "home-readiness", "benchmarks"]


@pytest.mark.parametrize("loc", ["fi", "sv"])
@pytest.mark.parametrize("cid", DEMO_IDS)
def test_no_english_in_localised_payloads(client, cid: str, loc: str) -> None:
    for route in ROUTES:
        res = client.get(f"/api/customers/{cid}/{route}", params={"locale": loc})
        assert res.status_code == 200, (route, res.text[:200])
        for s in _sentences(res.json()):
            assert detect_language(s, loc) == loc, f"{route}: English-looking text in {loc}: {s!r}"


def test_english_stays_english(client) -> None:
    data = client.get("/api/customers/CUST05020/baskets").json()
    assert data["labels"]["leak"] == "Everyday leaks"
    assert data["explanations"]["fixed"].startswith("Fixed essentials")


def test_swedish_rest_texts(client) -> None:
    b = client.get("/api/customers/CUST05020/baskets", params={"locale": "sv"}).json()
    assert b["labels"] == {"fixed": "Fasta måsten", "irregular": "Oregelbundna måsten", "leak": "Vardagsläckor"}
    assert b["rules"][0]["why"] == "Pengar som kommer in."
    nudges = client.get("/api/customers/CUST05020/nudges", params={"locale": "sv"}).json()
    assert nudges and all(detect_language(n["action_prompt"], "sv") == "sv" for n in nudges)
    prof = client.get("/api/customers/CUST05020/profile", params={"locale": "sv"}).json()
    assert prof["archetype"]["key"] == "latte_leaker" and prof["archetype"]["name"] == "Latteläckaren"
    sts = client.get("/api/customers/CUST05020/safe-to-spend", params={"locale": "sv"}).json()
    assert "lönedagen" in sts["explanation"] and re.search(r"\d \d{3},\d{2} €", sts["explanation"])
    tx = client.get("/api/customers/CUST05020/transactions", params={"locale": "sv", "limit": 50}).json()
    assert any(t["merchant_label"].startswith("Matbutik #") for t in tx["items"])
    demo = client.get("/api/customers/demo", params={"locale": "sv"}).json()
    assert all(detect_language(d["tagline"], "en") == "sv" or len(d["tagline"].split()) < 4 for d in demo)


def test_unknown_locale_falls_back_to_english(client) -> None:
    for route in ("/api/customers/CUST05020/nudges", "/api/lessons", "/api/personas", "/api/baskets/rules"):
        res = client.get(route, params={"locale": "de-DE"})
        assert res.status_code == 200, route
    assert client.get("/api/lessons", params={"locale": "de"}).json()["locale"] == "en"


def test_404_detail_is_localised(client) -> None:
    assert client.get("/api/customers/CUST99999/overview", params={"locale": "sv"}).json()["detail"].startswith("Okänd kund")
    assert client.get("/api/customers/CUST99999/overview", params={"locale": "fi"}).json()["detail"].startswith("Tuntematon")


def test_lessons_are_fully_swedish(client) -> None:
    data = client.get("/api/lessons", params={"locale": "sv"}).json()
    assert data["locale"] == "sv" and len(data["lessons"]) == 16
    for lesson in data["lessons"]:
        for key in ("title", "summary", "body", "key_takeaway", "unlock_hint"):
            assert isinstance(lesson[key], str) and lesson[key]
        assert detect_language(lesson["body"], "en") == "sv", lesson["id"]
        assert len(lesson["quiz"]["options"]) > lesson["quiz"]["answer_index"]
    assert detect_language(data["concepts"]["three-baskets"]["definition"], "en") == "sv"


def test_lessons_file_has_every_language() -> None:
    from app.config import APP_DATA_DIR

    missing: list[str] = []

    def walk(o: Any, path: str) -> None:
        if isinstance(o, dict):
            if "en" in o and "fi" in o and set(o) <= {"en", "fi", "sv"}:
                if "sv" not in o:
                    missing.append(path)
                return
            for k, v in o.items():
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")

    for name in ("lessons.json", "personas.json", "mcc.json"):
        walk(json.loads((APP_DATA_DIR / name).read_text(encoding="utf-8")), name)
    assert not missing


# ----------------------------------------------------------------------------- personas


def test_personas_are_human_and_trilingual(client) -> None:
    from app.config import APP_DATA_DIR

    raw = (APP_DATA_DIR / "personas.json").read_text(encoding="utf-8")
    assert not ANIMAL.search(raw)
    for loc in ("en", "fi", "sv"):
        data = client.get("/api/personas", params={"locale": loc}).json()
        ids = {p["id"] for p in data["personas"]}
        assert ids == {"sisu", "aava"}
        for p in data["personas"]:
            assert isinstance(p["title"], str) and isinstance(p["greeting"], list | str)


@pytest.mark.parametrize("loc", ["en", "fi", "sv"])
@pytest.mark.parametrize("persona_id", ["sisu", "aava"])
def test_system_prompt_has_no_animals(persona_id: str, loc: str) -> None:
    from app.agent.personas import get_persona
    from app.agent.prompts import UserContext, build_system_prompt

    prompt = build_system_prompt(get_persona(persona_id), loc, UserContext(name="Emma", age=21, as_of="2026-09-18", lines=["Name: Emma"]))
    assert not ANIMAL.search(prompt)
    assert {"en": "English", "fi": "Finnish", "sv": "Swedish"}[loc] in prompt


# ----------------------------------------------------------------------------- offline router


def test_swedish_router() -> None:
    from app.agent.fallback import parse_amounts, parse_deadline, route

    goal = route("hjälp mig spara till en bil som kostar 12 000 €", "sv", AS_OF)
    assert goal.calls == [("plan_goal", {"target_amount": 12000.0, "name": "Bil"})]
    surv = route("hur klarar jag månaden med 150 euro", "sv", AS_OF)
    assert surv.calls == [("survival_plan", {"amount": 150.0})]
    assert route("var läcker mina pengar", "sv", AS_OF).name == "baskets"
    assert route("Hurdan konsument är jag?", "sv", AS_OF).name == "profile"
    assert route("Hur mycket kan jag tryggt använda den här veckan?", "sv", AS_OF).name == "safe"
    what_if = route("Hur mycket sparar jag om jag minskar restaurangbesöken med 20 %?", "sv", AS_OF)
    assert what_if.calls[0][1]["adjustments"] == [{"change_pct": -20.0, "category": "Restaurants"}]
    spend = route("Hur mycket lade jag på taxi förra månaden?", "sv", AS_OF)
    assert spend.calls == [("query_spending", {"subcategory": "taxi", "period": "last_month"})]
    assert parse_amounts("300 euro") == [300.0]
    assert parse_amounts("12 000 kr") == []  # kronor are not euros
    assert parse_deadline("senast i juni", AS_OF) == "2027-06-30"
    assert parse_deadline("om 18 månader", AS_OF) == "2028-03-18"
    created = route("ja, skapa målet", "sv", AS_OF, history=["spara till en resa 3 000 euro senast i juni"])
    assert created.calls == [("create_goal", {"target_amount": 3000.0, "name": "Resa", "deadline": "2027-06-30", "kind": "travel"})]


def test_swedish_consent_is_language_aware() -> None:
    from app.agent.tools import user_confirmed

    assert user_confirmed("ja, skapa målet")
    assert user_confirmed("Ja tack")
    assert not user_confirmed("säästä autoon ja matkaan")  # Finnish "ja" = "and"
    assert not user_confirmed("hjälp mig spara till en bil")


# ----------------------------------------------------------------------------- chat turns


async def _turn(text: str, locale: str, monkeypatch, persona: str = "sisu", cid: str = "CUST05020") -> dict[str, Any]:
    from app.agent.orchestrator import run_chat

    monkeypatch.setenv("LLM_OFFLINE", "1")
    req = ChatRequest(customer_id=cid, persona=persona, locale=locale, messages=[{"role": "user", "content": text}])
    out: dict[str, Any] = {"text": "", "labels": [], "widgets": [], "done": None}
    async for e in run_chat(req):
        if e.event == "token":
            out["text"] += e.data["text"]
        elif e.event == "status":
            out["labels"].append(e.data["label"])
        elif e.event == "widget":
            out["widgets"].append(e.data)
        elif e.event == "done":
            out["done"] = e.data
    return out


@pytest.mark.parametrize(
    ("text", "locale", "expected"),
    [
        ("Hur mycket lade jag på mat förra månaden?", "sv", "sv"),
        ("Hur mycket lade jag på mat förra månaden?", "fi", "sv"),  # wrote Swedish in a Finnish app
        ("How much did I spend on groceries last month?", "sv", "en"),
        ("Paljonko käytin ruokaan viime kuussa?", "en", "fi"),
        ("ok", "sv", "sv"),  # too short to tell: the app locale decides
    ],
)
async def test_answer_follows_the_users_language(monkeypatch, text: str, locale: str, expected: str) -> None:
    out = await _turn(text, locale, monkeypatch)
    assert detect_language(out["text"], locale) == expected, out["text"]
    for chip in out["done"]["suggestions"]:
        assert detect_language(chip, expected) == expected, chip


async def test_swedish_turn_is_swedish_end_to_end(monkeypatch) -> None:
    out = await _turn("Hur klarar jag månaden med 150 euro?", "sv", monkeypatch, persona="aava", cid="CUST00584")
    assert not ANIMAL.search(out["text"] + " ".join(out["labels"]))
    assert all(detect_language(label, "en") == "sv" or len(label.split()) < 3 for label in out["labels"]), out["labels"]
    plan = next(w for w in out["widgets"] if w["type"] == "survival_plan")["data"]
    assert all(detect_language(t, "en") == "sv" for t in plan["tips"]), plan["tips"]
    assert "lönedagen" in out["text"] or "fram till" in out["text"]


async def test_swedish_goal_plan_widgets(monkeypatch) -> None:
    out = await _turn("hjälp mig spara till en bil som kostar 12 000 € senast i juni", "sv", monkeypatch)
    buttons = next(w for w in out["widgets"] if w["type"] == "action_buttons")["data"]["buttons"]
    assert buttons[0]["label"].startswith("Skapa målet 'Bil'")
    plan = next(w for w in out["widgets"] if w["type"] == "goal_plan")["data"]
    assert detect_language(plan["summary"], "en") == "sv"
