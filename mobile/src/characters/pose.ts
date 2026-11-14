/**
 * Per-frame pose of one character, derived on the UI thread from the shared
 * clock and the state weights. Computed once per frame and read by every
 * animated layer / prop, so each layer's worklet is a couple of field reads.
 */
import { useDerivedValue, type SharedValue } from 'react-native-reanimated';

import type { BrowCurve, MouthKey, PersonaArt } from './art/types';
import {
  LEAN,
  POSES,
  clamp,
  emphasis,
  fract,
  hop,
  idleGaze,
  smooth,
  talkFrame,
} from './motion';
import type { HumanRig } from './rig';
import { CHARACTER_STATES } from './types';

export type MouthMix = Record<MouthKey, number>;

export interface Pose {
  t: number;
  mouth: MouthMix;
  /** Pupil offset (units). */
  gx: number;
  gy: number;
  /** Brow path strings (viewer-left, viewer-right). */
  browL: string;
  browR: string;
  lidHalf: number;
  lidClosed: number;
  lidHappy: number;
  /** Extra head rotation (deg) and vertical bob (units). */
  tilt: number;
  bob: number;
  /** Whole-figure lift (units, negative = up) and scale. */
  y: number;
  sx: number;
  sy: number;
  /** Gesture arm: 0..1 visibility, extra rotation (deg). */
  gesture: number;
  pump: number;
  /** Aava's glasses slip (units), Sisu's sweat-drop progress 0..1. */
  glasses: number;
  sweat: number;
  sparkle: number;
}

const TALK_KEYS: readonly MouthKey[] = ['calm', 'talkA', 'talkO', 'smile'];

function curveD(c: number[]): string {
  'worklet';
  return `M${c[0].toFixed(2)} ${c[1].toFixed(2)} Q${c[2].toFixed(2)} ${c[3].toFixed(2)} ${c[4].toFixed(2)} ${c[5].toFixed(2)}`;
}

export function usePose(rig: HumanRig, browsData: PersonaArt['brows']): SharedValue<Pose> {
  const { clock, phase, w, blink, entry, profile, persona, reduced } = rig;
  const lean = LEAN[persona];
  const isAava = persona === 'aava';
  const amp = reduced ? 0.2 : 1;
  // Plain data only: worklets cannot capture the art's React components.
  const brows: Record<string, readonly [BrowCurve, BrowCurve]> = {
    neutral: browsData.neutral,
    raised: browsData.raised,
    concerned: browsData.concerned,
    thinking: browsData.thinking,
  };

  return useDerivedValue<Pose>(() => {
    const t = clock.value + phase;
    const W: Record<string, number> = {
      idle: w.idle.value,
      listening: w.listening.value,
      thinking: w.thinking.value,
      talking: w.talking.value,
      happy: w.happy.value,
      concerned: w.concerned.value,
      celebrate: w.celebrate.value,
    };

    // --- mouth, brows, gaze, tilt: weighted sums of the per-state poses -----
    const mouth: MouthMix = { smile: 0, calm: 0, talkA: 0, talkO: 0, grin: 0, concerned: 0, hmm: 0 };
    const bl = [0, 0, 0, 0, 0, 0];
    const br = [0, 0, 0, 0, 0, 0];
    let gx = 0;
    let gy = 0;
    let tilt = 0;
    for (let i = 0; i < CHARACTER_STATES.length; i++) {
      const s = CHARACTER_STATES[i];
      const ws = W[s];
      if (ws <= 0.0001) continue;
      const P = POSES[s];
      if (P.mouth === 'talk') {
        mouth[TALK_KEYS[talkFrame(t, profile.talkRate)]] += ws;
      } else {
        mouth[P.mouth] += ws;
      }
      const b = brows[P.brows];
      for (let j = 0; j < 6; j++) {
        bl[j] += ws * b[0][j];
        br[j] += ws * b[1][j];
      }
      gx += ws * P.gaze[0];
      gy += ws * P.gaze[1];
      tilt += ws * P.tilt * profile.tiltScale * lean;
    }

    const emph = emphasis(t, profile.talkRate);
    // Brow accents on stressed syllables while talking; a curious lift while listening.
    const browLift = -2.6 * emph * emph * W.talking - 1.2 * W.listening * (0.5 + 0.5 * Math.sin(t * 1.3));
    bl[1] += browLift;
    bl[3] += browLift;
    bl[5] += browLift;
    br[1] += browLift;
    br[3] += browLift;
    br[5] += browLift;

    // Idle eyes glance around; talking keeps eye contact with small darts.
    const ig = idleGaze(t);
    gx += ig[0] * (W.idle + W.talking * 0.4 + W.happy * 0.3);
    gy += ig[1] * (W.idle + W.talking * 0.4);

    // --- head ----------------------------------------------------------------
    const swayW = W.idle + 0.5 * W.listening + 0.6 * W.talking + 0.5 * W.happy;
    tilt +=
      swayW * profile.swayDeg * Math.sin(t * 0.8) * amp +
      W.talking * 1.3 * Math.sin(t * 2.1 + Math.sin(t * 0.9)) * amp +
      W.thinking * 1.2 * Math.sin(t * 0.55) * amp;
    const bob =
      W.talking * profile.talkBob * emph * amp -
      W.listening * 1.4 * (0.5 + 0.5 * Math.sin(t * 1.6)) * amp +
      W.concerned * 2;

    // --- body: breathing, happy bounce, celebrate hops ----------------------
    const breath = 0.5 + 0.5 * Math.sin((2 * Math.PI * t) / profile.breathPeriod);
    let sy = 1 + 0.012 * breath;
    let sx = 1 + 0.004 * breath;
    const hp = hop(t, profile.hopRate);
    const happyEnv = W.happy * (0.15 + 0.85 * (1 - entry.value)) * amp;
    const jp = hop(t, profile.jumpRate);
    const celebEnv = W.celebrate * amp;
    let y = -profile.hopHeight * hp[0] * happyEnv - profile.jumpHeight * jp[0] * celebEnv;
    const sq = profile.squash * (hp[1] * happyEnv + jp[1] * celebEnv);
    sy *= 1 - sq;
    sx *= 1 + sq * 0.6;
    y += W.concerned * 1.5;

    // --- lids: blink frames (half → closed), happy ^ ^ eyes ------------------
    const lidHappy = clamp(W.happy + (isAava ? W.celebrate : 0), 0, 1);
    const b = blink.value;
    const open = 1 - lidHappy;
    const lidClosed = clamp((b - 0.55) / 0.2, 0, 1) * open;
    const lidHalf = clamp((b - 0.15) / 0.15, 0, 1) * open;

    // --- gesture arm ---------------------------------------------------------
    const g = W.celebrate;
    const beat = Math.sin(2 * Math.PI * t * profile.pumpRate);
    const pump = isAava ? profile.pumpDeg * beat * amp : -profile.pumpDeg * Math.max(0, beat) * amp;

    // --- concerned extras ------------------------------------------------------
    // Aava: glasses slowly slip, then get pushed back up.
    const gp = fract(t / 3.4);
    const slip = gp < 0.78 ? smooth(0.1, 0.78, gp) : 1 - smooth(0.78, 0.86, gp);
    const glasses = isAava ? slip * 3.2 * W.concerned * (reduced ? 0 : 1) : 0;
    const sweat = fract(t / 2.4);

    return {
      t,
      mouth,
      gx,
      gy,
      browL: curveD(bl),
      browR: curveD(br),
      lidHalf,
      lidClosed,
      lidHappy,
      tilt,
      bob,
      y,
      sx,
      sy,
      gesture: g,
      pump,
      glasses,
      sweat,
      sparkle: 0.55 + 0.45 * Math.sin(t * 5.2),
    };
  });
}
