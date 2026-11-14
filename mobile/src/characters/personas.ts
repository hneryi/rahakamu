/**
 * Persona metadata (SPEC §6 `PERSONAS`, §6b human characters).
 *
 * The two coaches share every tool and every number, but differ in pedagogy:
 * - Sisu, "The Trainer": a Finnish guy in his late 20s in an amber quarter-zip
 *   with a tablet full of charts. Energetic, encouraging: reps, streaks, wins.
 * - Aava, "The Mentor": a Finnish woman in her mid 30s in a teal cardigan with
 *   a notebook and a pencil in her bun. Calm and wise; she explains the why.
 * The split shows in colour, voice pitch/rate and the motion profile
 * (motion.ts: Sisu bouncier and faster, Aava calmer and slower).
 *
 * Keep `color` values in sync with `app/data/personas.json` in the backend.
 */
import type { ChatMood, CharacterLocale, CharacterState, PersonaId, PersonaMeta } from './types';

export const PERSONAS: Record<PersonaId, PersonaMeta> = {
  sisu: {
    id: 'sisu',
    name: 'Sisu',
    title: { en: 'The Trainer', fi: 'Valmentaja', sv: 'Tränaren' },
    tagline: {
      en: 'Your money workout buddy. Small reps, real streaks, big wins.',
      fi: 'Rahatreenikaverisi. Pieniä toistoja, oikeita putkia, isoja voittoja.',
      sv: 'Din träningskompis för ekonomin. Korta pass, långa sviter, stora vinster.',
    },
    role: { en: 'your trainer', fi: 'valmentajasi', sv: 'din tränare' },
    color: '#F5A524',
    accent: '#B56A10',
    tint: 'rgba(245,165,36,0.14)',
    emoji: '🏋️',
    voice: { pitch: 0.95, rate: 1.05 },
  },
  aava: {
    id: 'aava',
    name: 'Aava',
    title: { en: 'The Mentor', fi: 'Mentori', sv: 'Mentorn' },
    tagline: {
      en: 'Calm, curious and clear. Let’s understand the why behind your money.',
      fi: 'Rauhallinen ja selkeä. Ymmärretään yhdessä, miksi raha liikkuu.',
      sv: 'Lugn, nyfiken och tydlig. Tillsammans förstår vi varför pengarna går dit de går.',
    },
    role: { en: 'your mentor', fi: 'mentorisi', sv: 'din mentor' },
    color: '#3DD9B4',
    accent: '#12665A',
    tint: 'rgba(61,217,180,0.14)',
    emoji: '📚',
    voice: { pitch: 1.1, rate: 0.95 },
  },
};

/** Ordered list for pickers. */
export const PERSONA_LIST: readonly PersonaMeta[] = [PERSONAS.sisu, PERSONAS.aava];

/** Human-readable state names for accessibility labels. */
export const STATE_LABELS: Record<CharacterState, Record<CharacterLocale, string>> = {
  idle: { en: 'relaxed', fi: 'rentona', sv: 'avslappnad' },
  listening: { en: 'listening', fi: 'kuuntelee', sv: 'lyssnar' },
  thinking: { en: 'thinking', fi: 'miettii', sv: 'tänker' },
  talking: { en: 'talking', fi: 'puhuu', sv: 'pratar' },
  happy: { en: 'happy', fi: 'iloinen', sv: 'glad' },
  concerned: { en: 'concerned', fi: 'huolestunut', sv: 'bekymrad' },
  celebrate: { en: 'celebrating', fi: 'juhlii', sv: 'firar' },
};

/**
 * Accessibility label such as "Sisu, your trainer — thinking" /
 * "Sisu, valmentajasi — miettii". Screen-reader users get the same emotional
 * feedback sighted users get from motion.
 */
export function characterLabel(
  persona: PersonaId,
  state: CharacterState,
  locale: CharacterLocale = 'en',
): string {
  const p = PERSONAS[persona];
  const loc: CharacterLocale = p.role[locale] ? locale : 'en';
  return `${p.name}, ${p.role[loc]} — ${STATE_LABELS[state][loc]}`;
}

/** Map the SSE `done.mood` to the resting state the character should show afterwards. */
export function moodToState(mood: ChatMood | string | null | undefined): CharacterState {
  switch (mood) {
    case 'happy':
      return 'happy';
    case 'concerned':
      return 'concerned';
    case 'celebrate':
      return 'celebrate';
    default:
      return 'idle';
  }
}
