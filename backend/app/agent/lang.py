"""Locales and a tiny, dependency-free language detector (SPEC §5.6).

The backend speaks three languages: English (``en``), Finnish (``fi``) and Swedish
(``sv``). Two rules live here so every module applies them the same way:

* **Locale normalisation.** ``norm_locale`` maps anything a client sends ("sv-FI",
  "FI", ``None``, "de") to one of the three, falling back to English instead of
  raising — a wrong ``Accept-Language`` must never break a request.
* **Turn language.** The coach answers in the language the user's *latest message*
  is written in, not blindly in the app locale: a Swedish-speaking customer with the
  app set to Finnish who types Swedish gets Swedish. ``detect_language`` scores the
  message against small function-word lists plus a few orthographic cues (``å`` is
  Swedish; double vowels and case endings are Finnish) and returns the request locale
  whenever the evidence is thin ("ok", "300 €", "Taxi?").

Why not a library? Three closely scoped languages, short chat messages and a known
domain (money) make a 100-line heuristic both more predictable and easier to test than
a statistical model — and it adds no dependency to the S-mobiili integration.
"""

from __future__ import annotations

import re
from typing import TypeVar

LOCALES: tuple[str, ...] = ("en", "fi", "sv")
DEFAULT_LOCALE = "en"

T = TypeVar("T")


def norm_locale(locale: object) -> str:
    """Map any locale-ish value to ``en`` / ``fi`` / ``sv`` (unknown → ``en``)."""
    code = re.split(r"[-_]", str(locale or DEFAULT_LOCALE).strip().lower())[0]
    return code if code in LOCALES else DEFAULT_LOCALE


def pick(locale: object, en: T, fi: T, sv: T | None = None) -> T:
    """Choose the variant for ``locale``; Swedish falls back to English when absent."""
    loc = norm_locale(locale)
    if loc == "fi":
        return fi
    if loc == "sv" and sv is not None:
        return sv
    return en


# Function words and very common chat/money words. Words shared between two of the
# languages ("ja", "on", "en" — Swedish "a", Finnish "I don't" —, "i", "men", "me") are
# deliberately left out.
_WORDS: dict[str, frozenset[str]] = {
    "en": frozenset(
        """the a an is are am was were be been do does did what how much many my mine your you we they it this that these those
        and or but not no yes yeah to of for with from at by about than then there here have has had will would could should can
        may might must please help me spend spent spending save saved saving savings money month week year last next every
        afford safe survive where when why which who am i'm i've i'd don't doesn't can't kind where's what's let's show tell
        explain give make create goal buy cost costs euros leaking leak leaks into out up down more less most thanks thank hello hi hey
        car trip home loan bills rent salary payday budget compare people age own numbers""".split()
    ),
    "fi": frozenset(
        """mitä mikä miten miksi missä mihin mistä milloin kuinka paljon paljonko kuka minä mä sinä sä hän te olen olet ovat oli
        ei et emme että jos kun kuin mutta tai sekä myös vain nyt sitten vielä jo minun mun sinun sun minulla minulle
        minua minut tämä tämän tässä tästä tuo se sen ne niitä onko voinko voisinko voin voit voi haluan haluaisin
        auta kerro näytä selitä tee luo kyllä joo juu kiitos moi hei terve moikka rahaa rahat rahani rahaa rahoja euroa eurolla
        kuussa kuukaudessa viikossa viikolla vuodessa viime ensi tällä tänä tässä säästää säästän säästäisin säästämään
        käytin käytän käyttää kulutan kulutin kulutus kuluttaja millainen selviän pärjään varaa ostaa maksaa
        tavoite tavoitteen vuotaa vuodot korit palkka vuokra laskut asuntolaina autoon omilla luvuillani ikätoverini""".split()
    ),
    "sv": frozenset(
        """vad hur varför var vart när vilken vilka vem mycket många jag du vi ni de dom det den detta denna dessa är var varit
        vara har hade inte och eller att om som så också bara nu sedan redan än min mitt mina din ditt dina mig dig oss
        kan kunde skulle ska vill måste får hjälp hjälpa visa berätta förklara gör skapa tack hej hejsan tjena pengar pengarna
        månad månaden månader vecka veckan år året förra nästa denna varje spara sparar sparat sparande spenderade spenderar
        lägger lade använde använda utgifter utgifterna köpa kostar kosta råd klarar klara överleva tryggt säkert
        mål målet lön lönen hyra hyran räkningar räkningarna bolån bil resa läcker läckor läckage med på till från för av hos
        över under efter innan mellan utan mer mindre mest senast inom jämfört andra ålder egna siffror vilken sorts slags""".split()
    ),
}

#: One of these alone settles the language even in a one-word message.
_STRONG: dict[str, frozenset[str]] = {
    "en": frozenset({"thanks", "thank", "hello", "please", "what", "how", "why", "yes", "the"}),
    "fi": frozenset({"kiitos", "moi", "moikka", "terve", "kyllä", "joo", "miten", "mitä", "paljonko", "miksi", "selvä"}),
    "sv": frozenset({"tack", "hejsan", "tjena", "hur", "vad", "varför", "och", "jag", "inte", "snälla"}),
}

_TOKEN_RE = re.compile(r"[a-zåäöéü']+", re.IGNORECASE)
_FI_SUFFIX_RE = re.compile(
    r"(ssa|ssä|sta|stä|lla|llä|lta|ltä|lle|ksi|tta|ttä|nko|nkö|kaan|kään|ani|äni|asi|äsi|mme|tte|iin|een|aan|ään|oon|uun|yyn|isin|isit|isi)$"
)
#: Swedish derivational / definite endings (``rimlig``, ``sparandet``, ``räkningarna``).
_SV_SUFFIX_RE = re.compile(r"(lig|ligt|liga|het|heten|ning|ningen|ningar|arna|erna|orna|ande|ende|andet|aren|skap|igt)$")
_FI_DOUBLE_RE = re.compile(r"aa|ii|uu|yy|ää|öö|ee(?!n\b)|kk|tt(?!e)|uo|yö|äi|öi|ää")


def language_scores(text: str) -> dict[str, float]:
    """Evidence per language for ``text`` (exposed for tests and debugging)."""
    tokens = [t.lower().strip("'") for t in _TOKEN_RE.findall(text or "")]
    scores = {"en": 0.0, "fi": 0.0, "sv": 0.0}
    for tok in tokens:
        if not tok:
            continue
        for loc in LOCALES:
            if tok in _WORDS[loc]:
                scores[loc] += 1.0
            if tok in _STRONG[loc]:
                scores[loc] += 1.0
        if "å" in tok:
            scores["sv"] += 1.5
        if len(tok) >= 5:
            # Finnish morphology: case endings and long vowels/geminates.
            if _FI_SUFFIX_RE.search(tok) and tok not in _WORDS["en"] and tok not in _WORDS["sv"]:
                scores["fi"] += 0.5
            if _FI_DOUBLE_RE.search(tok) and "å" not in tok and tok not in _WORDS["en"] and tok not in _WORDS["sv"]:
                scores["fi"] += 0.25
            if _SV_SUFFIX_RE.search(tok) and tok not in _WORDS["en"] and tok not in _WORDS["fi"]:
                scores["sv"] += 0.5
    return scores


def detect_language(text: str | None, default: object = DEFAULT_LOCALE) -> str:
    """Language of ``text`` among en/fi/sv; ``default`` when unsure.

    "Unsure" means too little evidence (``ok``, ``300 €``, a bare merchant word) or a
    near tie between the two best candidates — then the app locale decides.
    """
    fallback = norm_locale(default)
    scores = language_scores(text or "")
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    (best, best_score), (_, second_score) = ranked[0], ranked[1]
    if best_score < 1.0:
        return fallback
    if best_score - second_score < 0.5:
        return fallback if scores[fallback] >= second_score else best
    return best
