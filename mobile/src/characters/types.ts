/**
 * Public types for the SPankkiBot character system (SPEC §6 / §6b).
 *
 * The characters are the "face" of the Personal Economic Trainer: the same
 * component is docked on the home screen (~110 px, idle most of the time) and
 * shown large at the top of the chat, where its state follows the SSE stream
 * (`status: thinking` → `token` stream = talking → `done.mood`).
 *
 * Keeping the vocabulary tiny (7 states, 2 personas) is deliberate: the chat
 * screen can map backend events to a state with a one-line switch, and any
 * future host app (e.g. S-mobiili) only needs to learn these names.
 */
import type { StyleProp, ViewStyle } from 'react-native';

/** The two AI coaches. Must match `persona` in `POST /api/chat` (SPEC §4.2). */
export type PersonaId = 'sisu' | 'aava';

/**
 * Animation/expression state.
 * - idle: breathing, random blinks, slight head sway, eyes glance around.
 * - listening: head tilts toward the user, brows up, pulsing halo ring (mic held, user typing).
 * - thinking: eyes look up to the side, one brow up, "hmm" mouth, three-dot bubble (tools running).
 * - talking: irregular mouth loop (closed / A / O) with head bob (tokens streaming / TTS).
 * - happy: big grin, smiling ^ ^ eyes, small bounce (`mood: happy`).
 * - concerned: brows tilt inward, small mouth; Sisu sweats, Aava's glasses slip and get pushed up.
 * - celebrate: gesture pose (Sisu thumbs-up + hop, Aava raised "idea" finger) + sparkles.
 */
export type CharacterState =
  | 'idle'
  | 'listening'
  | 'thinking'
  | 'talking'
  | 'happy'
  | 'concerned'
  | 'celebrate';

/** All states, in a stable order (used by the lab screen and tests). */
export const CHARACTER_STATES: readonly CharacterState[] = [
  'idle',
  'listening',
  'thinking',
  'talking',
  'happy',
  'concerned',
  'celebrate',
] as const;

/** Locales the character labels are translated into. */
export type CharacterLocale = 'en' | 'fi' | 'sv';

/** A string in every supported UI locale. */
export type Localized = Record<CharacterLocale, string>;

/** Static metadata for a persona — used by onboarding, settings, chat header and TTS. */
export interface PersonaMeta {
  id: PersonaId;
  /** Display name ("Sisu", "Aava"). */
  name: string;
  /** Role title, e.g. "The Trainer" / "Valmentaja". */
  title: Localized;
  /** One-line pitch for the persona picker. */
  tagline: Localized;
  /** Role phrase used in the accessibility label ("your trainer" / "valmentajasi"). */
  role: Localized;
  /** Primary brand colour of the persona (buttons, halo ring, chat accents). */
  color: string;
  /** Deep companion tone (text on `color`, outlines, gradients). */
  accent: string;
  /** Soft tint for surfaces/bubbles that belong to the persona (rgba). */
  tint: string;
  /** Emoji fallback where an SVG cannot be rendered (notifications, plain text). */
  emoji: string;
  /** expo-speech parameters so the two voices sound different (SPEC §5.3). */
  voice: { pitch: number; rate: number };
}

/** Props of the public `<Character/>` component. */
export interface CharacterProps {
  persona: PersonaId;
  state: CharacterState;
  /**
   * Height in px (default 120). The character is drawn in a size × size square:
   * up to 140 px it uses the head-and-shoulders avatar crop, above that the full
   * half-body bust. Pure vector, crisp from ~48 px to 260 px.
   */
  size?: number;
  /** Language of the accessibility label (default 'en'). */
  locale?: CharacterLocale;
  /** Fire a success haptic when entering `celebrate` (native only, default false). */
  haptics?: boolean;
  /** Override the generated accessibility label. */
  accessibilityLabel?: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

/** `done.mood` values from the chat SSE protocol (SPEC §4.2). */
export type ChatMood = 'happy' | 'neutral' | 'concerned' | 'celebrate';

/** Internal props every persona component receives from `<Character/>`. */
export interface PersonaComponentProps {
  persona: PersonaId;
  state: CharacterState;
  size: number;
  /** DOM-safe unique id prefix for SVG defs. */
  uid: string;
  label: string;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}
