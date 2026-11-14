/**
 * Shape of a generated persona art module (art/sisu.tsx, art/aava.tsx).
 *
 * The art is transcribed 1:1 from design/characters/*.svg by tools/svg2rn.py.
 * All parts share the master coordinate system (viewBox 0 0 400 480), so the
 * animated layers can be stacked as full-size canvases.
 */
import type { ComponentType, ReactNode } from 'react';

/** Every art component takes the instance id prefix for its defs (`${p}clip-face`). */
export interface Pfx {
  p: string;
}

/** A brow as a quadratic curve: [x0, y0, cx, cy, x1, y1]. */
export type BrowCurve = readonly [number, number, number, number, number, number];
/** Viewer-left and viewer-right brow. */
export type BrowPair = readonly [BrowCurve, BrowCurve];

export interface PupilCircle {
  cx: number;
  cy: number;
  r: number;
  fill: string;
  opacity?: number;
}

export type MouthKey = 'smile' | 'calm' | 'talkA' | 'talkO' | 'grin' | 'concerned' | 'hmm';
export type LidKey = 'half' | 'closed' | 'happy';
export type BrowKey = 'neutral' | 'raised' | 'concerned' | 'thinking';

export interface PersonaArt {
  viewBox: string;
  /** Top-level clip paths and gradients; render once inside every <Svg> layer. */
  TopDefs: ComponentType<Pfx>;
  HairBack: ComponentType<Pfx>;
  Body: ComponentType<Pfx>;
  /** Arms in the rest pose; `armRight` slot replaces `#arm-right-rest` (hidden during the gesture). */
  ArmsRest: ComponentType<Pfx & { armRight: ReactNode }>;
  ArmRightRest: ComponentType<Pfx>;
  Ears: ComponentType<Pfx>;
  /** Face, shading, nose, blush (Sisu: beard), glasses temples. */
  Head: ComponentType<Pfx>;
  /** Eye whites + lid lines; the pupils are slots so they can look around. */
  Eyes: ComponentType<Pfx & { pupilLeft: ReactNode; pupilRight: ReactNode }>;
  HairFront: ComponentType<Pfx>;
  Glasses: ComponentType<Pfx>;
  /** Celebrate gesture arm (Sisu thumbs-up, Aava raised index finger). */
  ArmsGesture: ComponentType<Pfx & { sparkle?: ReactNode }>;
  IdeaSparkle: ComponentType<Pfx> | null;
  /** Persona lean, e.g. `rotate(4 202 280)`; applied to all head layers. */
  headTransform: string;
  /** Lean + 3/4 shift + lift for the mouth group. */
  mouthTransform: string;
  /** Lift of body / arm layers, e.g. `translate(0 -24)`. */
  bodyTransform: string;
  mouths: Record<MouthKey, ComponentType<Pfx>>;
  lids: Record<LidKey, ComponentType<Pfx>>;
  brows: { stroke: string; strokeWidth: number } & Record<BrowKey, BrowPair>;
  pupils: { left: readonly PupilCircle[]; right: readonly PupilCircle[] };
}
