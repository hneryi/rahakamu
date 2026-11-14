"""Post-answer signals: character mood, follow-up suggestion chips and merged sources.

Why rules instead of another LLM call?
These three things are shown *the instant* the answer finishes (``done`` event). A second
model round-trip would add latency on every message for little gain, and the inputs we
need are already structured: which tools ran and what they returned. Rules are also
predictable for the demo and testable.

* **Mood** drives the character animation and reinforces the lesson emotionally:
  a goal that is on track → *celebrate*; money running out before payday → *concerned*.
* **Suggestions** teach users what they can ask next — a guided path through the three
  baskets: spending → compare → simulate a cut → turn the saving into a goal.
  Sisu's chips lean to challenges, Aava's to understanding.
* **Sources** merge each tool's provenance into one "Based on N transactions · period"
  chip. Counts are summed over *distinct* analysis windows so two tools reading the same
  window do not double count.
"""

from __future__ import annotations

from typing import Any

from app.agent.lang import norm_locale, pick
from app.agent.tools import ToolResult
from app.agent.vocab import format_period, parse_iso

Mood = str  # "celebrate" | "happy" | "neutral" | "concerned"


def _status_of(name: str, result: ToolResult) -> dict[str, Any]:
    raw = result.raw if isinstance(result.raw, dict) else {}
    return raw


def derive_mood(results: list[tuple[str, ToolResult]], *, recovery_context: dict[str, Any] | None = None) -> Mood:
    """Pick the character's closing mood from tool outcomes (concerned > celebrate > happy)."""
    state = (recovery_context or {}).get("state")
    if state == "unknown":
        return "neutral"
    if state in ("balance_repair", "cashflow_stabilizing"):
        return "concerned"
    concerned = celebrate = happy = False
    for name, res in results:
        if res.error:
            continue
        raw = _status_of(name, res)
        if name == "safe_to_spend":
            status = raw.get("status")
            concerned |= status == "critical"
            happy |= status == "comfortable"
        elif name == "survival_plan":
            concerned |= raw.get("risk") == "short"
            happy |= raw.get("risk") == "ok"
        elif name == "plan_goal":
            celebrate |= raw.get("feasibility") == "on_track"
            happy |= raw.get("feasibility") == "stretch"
        elif name == "create_goal":
            celebrate |= (res.llm_payload or {}).get("status") == "saved"
        elif name == "home_readiness":
            celebrate |= raw.get("verdict") == "ready"
            happy |= raw.get("verdict") == "almost"
        elif name == "simulate_what_if":
            happy |= float(raw.get("monthly_saving") or 0) > 0
        elif name == "spender_profile":
            key = (raw.get("archetype") or {}).get("key")
            concerned |= key == "tightrope_walker"
            celebrate |= key in ("steady_planner", "squirrel_saver")
            happy = True
        elif name == "get_overview":
            sts = (raw.get("safe_to_spend") or {}).get("status")
            concerned |= sts == "critical"
            happy |= sts == "comfortable"
        elif name == "explain_concept":
            happy = True
        else:
            happy = True
    if concerned:
        return "concerned"
    if celebrate:
        return "celebrate"
    if happy:
        return "happy"
    return "neutral"


_SUGGEST: dict[str, dict[str, list[str]]] = {
    "query_spending": {
        "en": ["How does that compare with people my age?", "How much could I save if I cut it by 20%?", "Show my spending by month"],
        "fi": ["Miten tämä vertautuu ikätovereihini?", "Paljonko säästäisin, jos vähentäisin 20 %?", "Näytä kulutukseni kuukausittain"],
    },
    "search_transactions": {
        "en": ["How much is that per month?", "Which basket do these belong to?", "What is safe for me to spend this week?"],
        "fi": ["Paljonko se on kuukaudessa?", "Mihin koriin nämä kuuluvat?", "Paljonko voin turvallisesti käyttää tällä viikolla?"],
    },
    "get_baskets": {
        "en": ["What are my biggest leaks?", "How much could I save if I cut leaks by 20%?", "What kind of spender am I?"],
        "fi": ["Mitkä ovat suurimmat vuotoni?", "Paljonko säästäisin, jos vähentäisin vuotoja 20 %?", "Millainen kuluttaja olen?"],
    },
    "safe_to_spend": {
        "en": ["How do I survive until payday?", "Which bills are coming up?", "Where can I cut this week?"],
        "fi": ["Miten pärjään palkkapäivään asti?", "Mitä laskuja on tulossa?", "Mistä voin karsia tällä viikolla?"],
    },
    "recurring_payments": {
        "en": ["Which of these are leaks?", "What if I cancelled one subscription?", "Explain subscription creep"],
        "fi": ["Mitkä näistä ovat vuotoja?", "Entä jos peruisin yhden tilauksen?", "Selitä tilausten hiipivä kasvu"],
    },
    "spender_profile": {
        "en": ["What are my biggest leaks?", "Am I spending more than people my age?", "How can I become a steady planner?"],
        "fi": ["Mitkä ovat suurimmat vuotoni?", "Kulutanko enemmän kuin ikätoverini?", "Miten minusta tulee suunnitelmallinen?"],
    },
    "benchmarks": {
        "en": ["How much could I save if I matched the median?", "Explain the three baskets with my numbers", "What kind of spender am I?"],
        "fi": ["Paljonko säästäisin mediaanin tasolla?", "Selitä kolme koria luvuillani", "Millainen kuluttaja olen?"],
    },
    "simulate_what_if": {
        "en": ["Turn that saving into a goal", "What if I invested it at 4% a year?", "What else could I cut?"],
        "fi": ["Tee säästöstä tavoite", "Entä jos sijoittaisin sen 4 % vuosituotolla?", "Mistä muusta voisin karsia?"],
    },
    "plan_goal": {
        "en": ["Yes, create this goal", "What if I give it 6 more months?", "Which leaks should I cut first?"],
        "fi": ["Kyllä, luo tämä tavoite", "Entä jos annan 6 kuukautta lisää?", "Mitkä vuodot kannattaa karsia ensin?"],
    },
    "create_goal": {
        "en": ["What is safe for me to spend this week?", "Show my goals", "How can I speed this goal up?"],
        "fi": ["Paljonko voin turvallisesti käyttää tällä viikolla?", "Näytä tavoitteeni", "Miten nopeutan tavoitetta?"],
    },
    "list_goals": {
        "en": ["How can I reach my goals faster?", "Help me save for a trip", "What is safe for me to spend this week?"],
        "fi": ["Miten saavutan tavoitteeni nopeammin?", "Auta säästämään matkaan", "Paljonko voin turvallisesti käyttää tällä viikolla?"],
    },
    "survival_plan": {
        "en": ["Which bills are coming up?", "Where do I usually overspend?", "Explain the emergency fund"],
        "fi": ["Mitä laskuja on tulossa?", "Missä yleensä ylitän budjetin?", "Selitä puskurirahasto"],
    },
    "home_readiness": {
        "en": ["Help me save for a down payment", "What would make me ready sooner?", "Explain how mortgages work"],
        "fi": ["Auta säästämään käsirahaa", "Mikä tekisi minusta valmiin nopeammin?", "Selitä asuntolainan perusteet"],
    },
    "explain_concept": {
        "en": ["Show this with my own numbers", "Explain the three baskets", "What kind of spender am I?"],
        "fi": ["Näytä tämä omilla luvuillani", "Selitä kolme koria", "Millainen kuluttaja olen?"],
    },
    "get_overview": {
        "en": ["What is safe for me to spend this week?", "Explain the three baskets with my numbers", "What kind of spender am I?"],
        "fi": ["Paljonko voin turvallisesti käyttää tällä viikolla?", "Selitä kolme koria luvuillani", "Millainen kuluttaja olen?"],
    },
}

#: Swedish chips, kept next to each other so a translator can review them in one place.
_SUGGEST_SV: dict[str, list[str]] = {
    "query_spending": ["Hur står det sig mot andra i min ålder?", "Hur mycket sparar jag om jag minskar det med 20 %?", "Visa mina utgifter per månad"],
    "search_transactions": ["Hur mycket blir det per månad?", "Vilken korg hör de här till?", "Hur mycket kan jag tryggt använda den här veckan?"],
    "get_baskets": ["Vilka är mina största läckor?", "Hur mycket sparar jag om jag minskar läckorna med 20 %?", "Hurdan konsument är jag?"],
    "safe_to_spend": ["Hur klarar jag mig till lönedagen?", "Vilka räkningar är på kommande?", "Var kan jag dra ner den här veckan?"],
    "recurring_payments": ["Vilka av de här är läckor?", "Tänk om jag sade upp en prenumeration?", "Förklara hur prenumerationer smyger sig på"],
    "spender_profile": ["Vilka är mina största läckor?", "Lägger jag ut mer pengar än andra i min ålder?", "Hur blir jag en stadig planerare?"],
    "benchmarks": ["Hur mycket skulle jag spara på mediannivå?", "Förklara de tre korgarna med mina siffror", "Hurdan konsument är jag?"],
    "simulate_what_if": ["Gör ett sparmål av den besparingen", "Tänk om jag investerade det med 4 % årlig avkastning?", "Vad mer kunde jag dra ner på?"],
    "plan_goal": ["Ja, skapa det här målet", "Tänk om jag ger det 6 månader till?", "Vilka läckor ska jag täppa till först?"],
    "create_goal": ["Hur mycket kan jag tryggt använda den här veckan?", "Visa mina mål", "Hur når jag målet snabbare?"],
    "list_goals": ["Hur når jag mina mål snabbare?", "Hjälp mig spara till en resa", "Hur mycket kan jag tryggt använda den här veckan?"],
    "survival_plan": ["Vilka räkningar är på kommande?", "Var brukar jag gå över budgeten?", "Förklara vad en buffert är"],
    "home_readiness": ["Hjälp mig spara till en egen insats", "Vad skulle göra mig redo snabbare?", "Förklara grunderna i bolån"],
    "explain_concept": ["Visa det här med mina egna siffror", "Förklara de tre korgarna", "Hurdan konsument är jag?"],
    "get_overview": ["Hur mycket kan jag tryggt använda den här veckan?", "Förklara de tre korgarna med mina siffror", "Hurdan konsument är jag?"],
}
for _tool, _chips in _SUGGEST_SV.items():
    _SUGGEST[_tool]["sv"] = _chips
assert set(_SUGGEST_SV) == set(_SUGGEST), "every tool needs Swedish follow-up chips"

_PERSONA_CHIP = {
    "sisu": {"en": "Give me a 7-day challenge", "fi": "Anna minulle 7 päivän haaste", "sv": "Ge mig en 7-dagarsutmaning"},
    "aava": {"en": "Why do small purchases add up?", "fi": "Miksi pienet ostokset kertyvät?", "sv": "Varför växer små köp till stora summor?"},
}

_DEFAULT = {
    "en": ["What kind of spender am I?", "What is safe for me to spend this week?", "Explain the three baskets with my numbers"],
    "fi": ["Millainen kuluttaja olen?", "Paljonko voin turvallisesti käyttää tällä viikolla?", "Selitä kolme koria luvuillani"],
    "sv": ["Hurdan konsument är jag?", "Hur mycket kan jag tryggt använda den här veckan?", "Förklara de tre korgarna med mina siffror"],
}


def suggest_followups(tools_used: list[str], persona: str, locale: str, user_text: str = "", results: list[tuple[str, ToolResult]] | None = None, *, recovery_context: dict[str, Any] | None = None) -> list[str]:
    """Return exactly three follow-up questions in the user's language."""
    loc = norm_locale(locale)
    if (recovery_context or {}).get("state") in ("balance_repair", "cashflow_stabilizing", "unknown"):
        return {
            "en": ["Which bills are coming up?", "Where does the six-month spending gap come from?", "How do I make it to payday?"],
            "fi": ["Mitä laskuja on tulossa?", "Mistä kuuden kuukauden menoero muodostuu?", "Miten selviän palkkapäivään asti?"],
            "sv": ["Vilka räkningar är på väg?", "Var kommer utgiftsgapet på sex månader från?", "Hur klarar jag mig till lönedagen?"],
        }[loc]
    picks: list[str] = []
    # most informative tool = the last non-trivial one
    for name in reversed(tools_used):
        if name in ("render_chart",):
            continue
        picks.extend(_SUGGEST.get(name, {}).get(loc, []))
        break
    # if a plan was unrealistic, offer the later deadline first
    for name, res in results or []:
        if (name == "plan_goal" and isinstance(res.raw, dict) and res.raw.get("feasibility") == "unrealistic"
                and res.raw.get("suggested_deadline")):  # no date to offer when even cuts leave a deficit
            picks.insert(0, pick(loc, "What would be a realistic deadline?", "Mikä olisi realistinen aikataulu?", "Vad vore en realistisk tidsplan?"))
        if name in ("create_goal", "plan_goal") and (res.llm_payload or {}).get("status") == "saved":
            picks = [p for p in picks if not any(w in p.lower() for w in ("create", "luo", "skapa"))]
    persona_chip = _PERSONA_CHIP.get(persona, {}).get(loc)
    out: list[str] = []
    asked = (user_text or "").strip().lower()
    for item in picks[:2] + ([persona_chip] if persona_chip else []) + picks[2:] + _DEFAULT[loc]:
        if item and item.lower() != asked and item not in out:
            out.append(item)
        if len(out) == 3:
            break
    return out


def merge_sources(results: list[tuple[str, ToolResult]], locale: str) -> dict[str, Any]:
    """Merge per-tool provenance into the ``done.sources`` object."""
    windows: dict[tuple[str | None, str | None], int] = {}
    starts, ends = [], []
    tools: list[str] = []
    for name, res in results:
        if name not in tools:
            tools.append(name)
        src = res.sources or {}
        count = int(src.get("tx_count") or 0)
        key = (src.get("start"), src.get("end"))
        if count:
            windows[key] = max(windows.get(key, 0), count)
        s, e = parse_iso(src.get("start")), parse_iso(src.get("end"))
        if s:
            starts.append(s)
        if e:
            ends.append(e)
    period = format_period(min(starts) if starts else None, max(ends) if ends else None, locale) if (starts or ends) else ""
    if not starts and not ends:
        # fall back to any pre-formatted period string
        period = next((r.sources.get("period") for _, r in results if r.sources and r.sources.get("period")), "")
    return {"tx_count": sum(windows.values()), "period": period, "tools": tools}
