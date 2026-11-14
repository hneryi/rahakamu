/**
 * Animation rig for the human characters.
 *
 * 1. One shared clock. A single module-level shared value runs a linear
 *    UI-thread animation while at least one character is mounted. Every
 *    periodic motion (breathing, sway, talk loop, hops, sparkles) is a pure
 *    function of `clock + phase`, so N characters cost one animation, there
 *    are no per-part loops to keep in sync, and React never re-renders while
 *    animating.
 * 2. Blend, never snap. Each state has a 0..1 weight eased with withTiming on
 *    state changes (persona blendMs). Poses are weighted sums of the per-state
 *    poses, so thinking → talking → happy morphs smoothly.
 * 3. Platform-safe. Layer transforms go on Animated.View (works the same on
 *    iOS, Android and web); SVG animated props are limited to opacity, circle
 *    cx/cy and path d, which react-native-svg supports natively and on web.
 */
import { useEffect, useMemo, useState } from 'react';
import {
  cancelAnimation,
  Easing,
  makeMutable,
  ReduceMotion,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';

import { MOTION, type MotionProfile } from './motion';
import { CHARACTER_STATES, type CharacterState, type PersonaId } from './types';

// ---------------------------------------------------------------------------
// Shared clock
// ---------------------------------------------------------------------------

const CLOCK_PERIOD_S = 100_000; // ~28 h before the clock wraps
const clock = makeMutable(0);
let clockUsers = 0;

function startClock() {
  clock.value = 0;
  clock.value = withRepeat(
    withTiming(CLOCK_PERIOD_S, {
      duration: CLOCK_PERIOD_S * 1000,
      easing: Easing.linear,
      // The clock must keep running even with "reduce motion"; amplitudes are
      // reduced separately (see `reduced`).
      reduceMotion: ReduceMotion.Never,
    }),
    -1,
    false,
  );
}

/** Seconds since the first character mounted; shared by every character on screen. */
export function useSharedClock(): SharedValue<number> {
  useEffect(() => {
    if (clockUsers++ === 0) startClock();
    return () => {
      if (--clockUsers === 0) cancelAnimation(clock);
    };
  }, []);
  return clock;
}

// ---------------------------------------------------------------------------
// Rig
// ---------------------------------------------------------------------------

export type StateWeights = Record<CharacterState, SharedValue<number>>;

export interface HumanRig {
  /** Shared clock (s). Add `phase` before use. */
  clock: SharedValue<number>;
  /** Per-instance random phase so two characters never move in lockstep. */
  phase: number;
  w: StateWeights;
  /** Eyelid closure 0..1 from the random blink scheduler. */
  blink: SharedValue<number>;
  /** 0 → 1 over ~1.6 s after each state change (decaying entrance effects). */
  entry: SharedValue<number>;
  profile: MotionProfile;
  persona: PersonaId;
  /** OS "reduce motion": big displacements off, expressions still change. */
  reduced: boolean;
}

/** Keeps `value` around for `ms` after it changes away (lets layers fade out before unmounting). */
export function useLingerSet<T>(current: readonly T[], ms: number): T[] {
  const key = current.join('|');
  const [extra, setExtra] = useState<T[]>([]);
  const [prev, setPrev] = useState<readonly T[]>(current);
  if (prev.join('|') !== key) {
    // State changed: keep the previous items alive for the blend.
    setExtra([...prev.filter((v) => !current.includes(v))]);
    setPrev(current);
  }
  useEffect(() => {
    if (extra.length === 0) return undefined;
    const id = setTimeout(() => setExtra([]), ms);
    return () => clearTimeout(id);
  }, [extra, ms]);
  return useMemo(() => [...current, ...extra.filter((v) => !current.includes(v))], [current, extra]);
}

export function useHumanRig(state: CharacterState, persona: PersonaId): HumanRig {
  const profile = MOTION[persona];
  const reduced = useReducedMotion();
  const clockValue = useSharedClock();
  const [phase] = useState(() => Math.random() * 1000);

  const idle = useSharedValue(state === 'idle' ? 1 : 0);
  const listening = useSharedValue(state === 'listening' ? 1 : 0);
  const thinking = useSharedValue(state === 'thinking' ? 1 : 0);
  const talking = useSharedValue(state === 'talking' ? 1 : 0);
  const happy = useSharedValue(state === 'happy' ? 1 : 0);
  const concerned = useSharedValue(state === 'concerned' ? 1 : 0);
  const celebrate = useSharedValue(state === 'celebrate' ? 1 : 0);
  const w = useMemo<StateWeights>(
    () => ({ idle, listening, thinking, talking, happy, concerned, celebrate }),
    [idle, listening, thinking, talking, happy, concerned, celebrate],
  );
  const blink = useSharedValue(0);
  const entry = useSharedValue(1);

  useEffect(() => {
    const cfg = { duration: profile.blendMs, easing: Easing.inOut(Easing.cubic) };
    CHARACTER_STATES.forEach((s) => {
      w[s].value = withTiming(s === state ? 1 : 0, cfg);
    });
    entry.value = 0;
    entry.value = withTiming(1, { duration: 1600, easing: Easing.out(Easing.quad) });
    // A blink on attention shifts reads as "noticing" the user.
    if (state === 'listening' || state === 'thinking') {
      blink.value = withSequence(withTiming(1, { duration: 70 }), withTiming(0, { duration: 120 }));
    }
  }, [state, profile.blendMs, w, blink, entry]);

  // Random blinks every 2.5–5 s, sometimes a double blink.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      timer = setTimeout(
        () => {
          const close = withTiming(1, { duration: 60, easing: Easing.in(Easing.quad) });
          const hold = withTiming(1, { duration: 40 });
          const open = withTiming(0, { duration: 110, easing: Easing.out(Easing.quad) });
          blink.value =
            Math.random() < 0.18
              ? withSequence(close, open, close, hold, open)
              : withSequence(close, hold, open);
          schedule();
        },
        2500 + Math.random() * 2500,
      );
    };
    schedule();
    return () => clearTimeout(timer);
  }, [blink]);

  return useMemo(
    () => ({ clock: clockValue, phase, w, blink, entry, profile, persona, reduced }),
    [clockValue, phase, w, blink, entry, profile, persona, reduced],
  );
}
