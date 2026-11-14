/**
 * Language helpers shared by speech-to-text and text-to-speech.
 *
 * - BCP-47 tags per app locale (recognition and synthesis prefer different
 *   regional variants: Finland-Swedish voices are rare, Sweden-Swedish common).
 * - `detectLanguage()`: a tiny, dependency-free guess of whether a reply is
 *   Finnish, Swedish or English, so read-aloud uses a matching voice even when
 *   the coach answers in a different language than the UI (the agent replies in
 *   the language of the question).
 * - `pickVoice()`: ranks the platform's voices for a language.
 */
import type { Locale } from '@/api/types';

/** Speech-to-text tag (SPEC §5.6). */
export const STT_TAG: Record<Locale, string> = { fi: 'fi-FI', en: 'en-US', sv: 'sv-SE' };

/** Text-to-speech tags in order of preference. */
export const TTS_TAGS: Record<Locale, string[]> = { fi: ['fi-FI'], en: ['en-US', 'en-GB'], sv: ['sv-SE', 'sv-FI'] };

/** Pill order: one tap cycles FI → EN → SV → FI. */
export const VOICE_CYCLE: Locale[] = ['fi', 'en', 'sv'];
export const nextVoiceLang = (l: Locale): Locale => VOICE_CYCLE[(VOICE_CYCLE.indexOf(l) + 1) % VOICE_CYCLE.length];

// Short, frequent function words that are (nearly) unique to each language.
// Ambiguous ones ("on", "i", "min", "en", "a") are left out on purpose.
const WORDS: Record<Locale, Set<string>> = {
  en: new Set('the and you your is are to of in for that this it with what how my me can do much have be at from will would month week money spend save'.split(' ')),
  fi: new Set('ja ei se että olen olet sinun minun mitä miten paljonko voin kun tämä tässä kuussa mutta myös jos niin vain kanssa sinulla minulla euroa kuukaudessa joka ovat sinä minä tällä viikolla rahaa voit sitten'.split(' ')),
  sv: new Set('och att är jag du det som för med på inte har kan din ditt dina mig mitt vad hur den här till om av ett mycket månaden veckan också men så eller dig vi ska'.split(' ')),
};

const FI_SUFFIX = /(ssa|ssä|sta|stä|lla|llä|lle|lta|ltä|ksi|aan|ään)$/;

/** Best guess of the language of `text`; `fallback` when the text gives too little signal. */
export function detectLanguage(text: string, fallback: Locale): Locale {
  const lower = text.toLowerCase();
  const tokens = lower.split(/[^a-zåäöéüõ]+/).filter(Boolean);
  const score: Record<Locale, number> = { en: 0, fi: 0, sv: 0 };
  for (const tok of tokens) {
    for (const l of VOICE_CYCLE) if (WORDS[l].has(tok)) score[l] += 1;
    if (tok.length > 4 && FI_SUFFIX.test(tok)) score.fi += 0.5;
    if (/(aa|ää|uu|yy|ii|oo|öö)/.test(tok)) score.fi += 0.3;
  }
  score.sv += Math.min(4, (lower.match(/å/g) ?? []).length);
  const ranked = (Object.keys(score) as Locale[]).sort((a, b) => score[b] - score[a]);
  const best = ranked[0];
  if (score[best] < 2) return fallback;
  if (score[best] === score[ranked[1]]) return score[fallback] === score[best] ? fallback : best;
  return best;
}

export type VoiceLike = { identifier: string; name: string; language: string; quality?: string; localService?: boolean; isDefault?: boolean };

const norm = (tag: string) => tag.replace('_', '-').toLowerCase();

/**
 * Highest-ranked voice for `locale`, or null. Prefers the exact regional tag,
 * then "enhanced / natural / neural / premium" voices, then on-device ones;
 * robotic engines (eSpeak, compact) go last.
 */
export function pickVoice<V extends VoiceLike>(voices: V[], locale: Locale): V | null {
  const tags = TTS_TAGS[locale].map(norm);
  let best: V | null = null;
  let bestScore = -Infinity;
  for (const v of voices) {
    const lang = norm(v.language ?? '');
    if (lang.slice(0, 2) !== locale) continue;
    let s = 0;
    const exact = tags.indexOf(lang);
    s += exact === 0 ? 30 : exact > 0 ? 20 : 10;
    if (v.quality === 'Enhanced') s += 20;
    if (/natural|neural|enhanced|premium|wavenet|siri/i.test(v.name)) s += 15;
    if (v.localService) s += 5;
    if (v.isDefault) s += 2;
    if (/espeak|compact|robot/i.test(v.name)) s -= 25;
    if (s > bestScore) {
      best = v;
      bestScore = s;
    }
  }
  return best;
}
