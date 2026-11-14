/**
 * Motion vocabulary for the human characters: per-persona motion profiles, the
 * state → pose table (from design/characters/tools/render.py STATES), and pure
 * worklet helpers. No React here, so the choreography is easy to tune.
 *
 * Units: art coordinates of the master SVG (viewBox 0 0 400 480), degrees.
 */
import type { BrowKey, MouthKey } from './art/types';
import type { CharacterState, PersonaId } from './types';

/** Per-persona motion personality. */
export interface MotionProfile {
  /** Duration of state blends (ms). Longer = calmer. */
  blendMs: number;
  /** Seconds per breath. */
  breathPeriod: number;
  /** Idle head sway amplitude (deg). */
  swayDeg: number;
  /** Multiplier on the per-state head tilts from the pose table. */
  tiltScale: number;
  /** Mouth frames per second while talking (TTS rate: Sisu 1.05, Aava 0.95). */
  talkRate: number;
  /** Head bob while talking (units). */
  talkBob: number;
  /** Happy bounce height (units) and hops / s. */
  hopHeight: number;
  hopRate: number;
  /** Celebrate hop height (units) and hops / s. Limited by the bust's bottom edge. */
  jumpHeight: number;
  jumpRate: number;
  /** Squash on landing (0..0.1). */
  squash: number;
  /** Gesture arm pump amplitude (deg) and rate (Hz) when celebrating. */
  pumpDeg: number;
  pumpRate: number;
}

export const MOTION: Record<PersonaId, MotionProfile> = {
  sisu: {
    blendMs: 260,
    breathPeriod: 2.8,
    swayDeg: 1.5,
    tiltScale: 1,
    talkRate: 8.6,
    talkBob: 2.2,
    hopHeight: 9,
    hopRate: 2.1,
    jumpHeight: 12,
    jumpRate: 1.5,
    squash: 0.04,
    pumpDeg: 7,
    pumpRate: 1.5,
  },
  aava: {
    blendMs: 520,
    breathPeriod: 4,
    swayDeg: 1,
    tiltScale: 1.1,
    talkRate: 6.8,
    talkBob: 1.3,
    hopHeight: 3.5,
    hopRate: 1.3,
    jumpHeight: 3.5,
    jumpRate: 0.75,
    squash: 0.015,
    pumpDeg: 3,
    pumpRate: 0.6,
  },
};

/** Persona lean direction: Sisu leans toward viewer-right (+), Aava toward viewer-left (−). */
export const LEAN: Record<PersonaId, 1 | -1> = { sisu: 1, aava: -1 };

export interface StatePose {
  /** Mouth variant, or 'talk' for the speech loop. */
  mouth: MouthKey | 'talk';
  brows: BrowKey;
  /** Pupil offset (units). */
  gaze: readonly [number, number];
  /** Extra head tilt in the persona's lean direction (deg). */
  tilt: number;
}

/** State → layer mapping, matching the approved renders (design/characters/NOTES.md). */
export const POSES: Record<CharacterState, StatePose> = {
  idle: { mouth: 'smile', brows: 'neutral', gaze: [0, 0], tilt: 0 },
  listening: { mouth: 'calm', brows: 'raised', gaze: [0, -1.5], tilt: 7 },
  thinking: { mouth: 'hmm', brows: 'thinking', gaze: [5, -5], tilt: -5 },
  talking: { mouth: 'talk', brows: 'neutral', gaze: [0, 0], tilt: 0 },
  happy: { mouth: 'grin', brows: 'raised', gaze: [0, 0], tilt: 2 },
  concerned: { mouth: 'concerned', brows: 'concerned', gaze: [0, 1.5], tilt: 3 },
  celebrate: { mouth: 'grin', brows: 'raised', gaze: [0, 0], tilt: 0 },
};

/** Mouth variants the talk loop uses (so only these get mounted while talking). */
export const TALK_MOUTHS: readonly MouthKey[] = ['calm', 'talkA', 'talkO', 'smile'];

/** Neck pivot for head tilts / nods (master SVG units). */
export const NECK: readonly [number, number] = [202, 280];

// ---------------------------------------------------------------------------
// Worklet helpers
// ---------------------------------------------------------------------------

export function clamp(v: number, lo: number, hi: number): number {
  'worklet';
  return v < lo ? lo : v > hi ? hi : v;
}

export function fract(v: number): number {
  'worklet';
  return v - Math.floor(v);
}

/** Cheap deterministic hash of an integer → [0, 1). */
export function hash1(n: number): number {
  'worklet';
  return fract(Math.sin(n * 127.1 + 311.7) * 43758.5453);
}

export function smooth(e0: number, e1: number, x: number): number {
  'worklet';
  const k = clamp((x - e0) / (e1 - e0), 0, 1);
  return k * k * (3 - 2 * k);
}

/**
 * Talk loop: which mouth to show at time t. Frames last irregular lengths (the
 * phase is warped by two sines), "syllables" pick A / O / calm by hash, and a
 * short phrase pause shows the closed smile every few seconds.
 * Returns 0 = calm, 1 = talkA, 2 = talkO, 3 = smile (pause).
 */
export function talkFrame(t: number, rate: number): number {
  'worklet';
  // Phrase pause: ~12 % of the time, in ~3.3 s phrases.
  const phrase = t / 3.3 + 0.25 * Math.sin(t * 0.7);
  if (fract(phrase) > 0.88) return 3;
  // Monotonic warped syllable clock (derivative stays > 0 for rate > 6).
  const s = t * rate + 0.6 * Math.sin(t * 2.3) + 0.25 * Math.sin(t * 5.3);
  const h = hash1(Math.floor(s));
  if (h < 0.3) return 0;
  if (h < 0.78) return 1;
  return 2;
}

/** Speech emphasis 0..1 used for head bob / brow accents (smooth, irregular). */
export function emphasis(t: number, rate: number): number {
  'worklet';
  const a = Math.sin(t * rate * 0.9) * 0.5 + 0.5;
  const b = Math.sin(t * rate * 0.37 + 1.3) * 0.5 + 0.5;
  return a * b;
}

/**
 * Idle gaze: holds a target for 1.4–3 s, then darts (saccade) to the next one.
 * Mostly looks at the user (centre), sometimes to the sides.
 */
export function idleGaze(t: number): [number, number] {
  'worklet';
  const seg = t / 2.2;
  const i = Math.floor(seg);
  const target = (k: number): [number, number] => {
    const h = hash1(k * 7.13);
    if (h < 0.55) return [0, 0];
    const a = hash1(k * 3.7 + 1) * Math.PI * 2;
    return [Math.cos(a) * 3, Math.sin(a) * 1.6];
  };
  const a = target(i - 1);
  const b = target(i);
  const k = smooth(0, 0.06, fract(seg));
  return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
}

/** Hop curve: |sin| arc with a short landing squash. Returns [lift 0..1, squash 0..1]. */
export function hop(t: number, rate: number): [number, number] {
  'worklet';
  const p = fract(t * rate);
  const lift = Math.sin(p * Math.PI);
  const squash = p < 0.12 ? Math.sin((p / 0.12) * Math.PI) : 0;
  return [lift, squash];
}
