/**
 * SPankkiBot characters (Sisu the Trainer, Aava the Mentor) — public API (SPEC §6 / §6b).
 * Everything else in this folder is an implementation detail.
 *
 *   import { Character, PERSONAS, moodToState, type CharacterState } from '@/characters';
 */
export { Character, DEFAULT_CHARACTER_SIZE } from './Character';
export { PERSONAS, PERSONA_LIST, STATE_LABELS, characterLabel, moodToState } from './personas';
export { CHARACTER_STATES } from './types';
export type {
  CharacterLocale,
  CharacterProps,
  CharacterState,
  ChatMood,
  Localized,
  PersonaId,
  PersonaMeta,
} from './types';
export { MOTION, type MotionProfile } from './motion';
