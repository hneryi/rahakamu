/**
 * Maps the master art coordinates (viewBox 0 0 400 480) into a size × size box.
 *
 * - Up to 140 px the head-and-shoulders avatar crop is used (design NOTES:
 *   "Small sizes (≤ 110 px): use the avatar crop"), above that the full bust.
 * - The crop is fitted to 94 % of the box height and anchored at the bottom,
 *   leaving headroom for hops and head tilts. The box clips (overflow hidden),
 *   so the bust always ends in a clean cut at the bottom edge.
 * - Every animated layer is a full "canvas": the crop padded on all sides, so
 *   rotated / lifted parts never hit an SVG viewport edge.
 */
import type { PersonaId } from './types';

type Rect = readonly [number, number, number, number];

const CROPS: Record<PersonaId, { full: Rect; avatar: Rect }> = {
  sisu: { full: [0, 0, 400, 480], avatar: [62, 22, 280, 300] },
  aava: { full: [0, 0, 400, 480], avatar: [58, 4, 280, 300] },
};

/** Sizes at or below this use the avatar crop. */
export const AVATAR_MAX_SIZE = 140;
const HEADROOM = 0.06;
const PAD_X = 70;
const PAD_T = 70;
const PAD_B = 80;

export interface CharacterLayout {
  size: number;
  avatar: boolean;
  /** px per art unit. */
  k: number;
  /** Canvas position / size in px inside the box. */
  canvas: { left: number; top: number; width: number; height: number };
  /** viewBox string of every layer <Svg>. */
  viewBox: string;
  /** Crop rect in art units. */
  crop: Rect;
  /** transformOrigin (percent of the canvas) for a pivot in art units. */
  origin: (x: number, y: number) => string;
  /** Art units → px inside the box. */
  toBox: (x: number, y: number) => [number, number];
}

export function computeLayout(persona: PersonaId, size: number): CharacterLayout {
  const avatar = size <= AVATAR_MAX_SIZE;
  const crop = avatar ? CROPS[persona].avatar : CROPS[persona].full;
  const [cx, cy, cw, ch] = crop;
  const k = (size * (1 - HEADROOM)) / ch;
  const left = (size - cw * k) / 2;
  const top = size - ch * k;
  const vx = cx - PAD_X;
  const vy = cy - PAD_T;
  const vw = cw + 2 * PAD_X;
  const vh = ch + PAD_T + PAD_B;
  return {
    size,
    avatar,
    k,
    crop,
    canvas: { left: left - PAD_X * k, top: top - PAD_T * k, width: vw * k, height: vh * k },
    viewBox: `${vx} ${vy} ${vw} ${vh}`,
    origin: (x, y) =>
      `${(((x - vx) / vw) * 100).toFixed(3)}% ${(((y - vy) / vh) * 100).toFixed(3)}%`,
    toBox: (x, y) => [left + (x - cx) * k, top + (y - cy) * k],
  };
}
