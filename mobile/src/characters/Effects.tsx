/**
 * Stage effects around a character: listening halo, thinking bubble and
 * celebrate sparkles. Plain Animated.Views (plus one tiny star SVG) driven by
 * the shared pose clock; each one mounts only while its state is active.
 */
import { memo } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, type SharedValue } from 'react-native-reanimated';
import Svg, { Path } from 'react-native-svg';

import { fract } from './motion';
import type { Pose } from './pose';

type PoseSV = SharedValue<Pose>;

// ---------------------------------------------------------------------------
// Listening halo: soft glow + two expanding rings behind the head
// ---------------------------------------------------------------------------

function Ring({
  pose,
  w,
  color,
  d,
  offset,
  reduced,
}: {
  pose: PoseSV;
  w: SharedValue<number>;
  color: string;
  d: number;
  offset: number;
  reduced: boolean;
}) {
  const style = useAnimatedStyle(() => {
    const p = reduced ? 0.35 : fract(pose.value.t * 0.75 + offset);
    return {
      opacity: w.value * (1 - p) * 0.7,
      transform: [{ scale: 0.82 + 0.3 * p }],
    };
  });
  return (
    <Animated.View
      style={[styles.ring, { width: d, height: d, borderRadius: d / 2, borderColor: color }, style]}
    />
  );
}

export function HaloRings({
  pose,
  w,
  color,
  center,
  radius,
  reduced,
}: {
  pose: PoseSV;
  w: SharedValue<number>;
  color: string;
  center: [number, number];
  radius: number;
  reduced: boolean;
}) {
  const d = radius * 2;
  const glow = useAnimatedStyle(() => ({
    opacity: w.value * (0.13 + 0.05 * Math.sin(pose.value.t * 2.4)),
  }));
  return (
    <View style={[styles.abs, { left: center[0] - radius, top: center[1] - radius, width: d, height: d }]}>
      <Animated.View style={[styles.abs, { width: d, height: d, borderRadius: radius, backgroundColor: color }, glow]} />
      <Ring pose={pose} w={w} color={color} d={d} offset={0} reduced={reduced} />
      {reduced ? null : <Ring pose={pose} w={w} color={color} d={d} offset={0.5} reduced={reduced} />}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Thinking bubble with three bouncing dots
// ---------------------------------------------------------------------------

function Dot({ pose, i, s, color }: { pose: PoseSV; i: number; s: number; color: string }) {
  const style = useAnimatedStyle(() => {
    const ph = pose.value.t * 5 - i * 0.7;
    const up = Math.max(0, Math.sin(ph));
    return {
      opacity: 0.45 + 0.55 * up,
      transform: [{ translateY: -up * s * 0.9 }],
    };
  });
  return (
    <Animated.View
      style={[{ width: s, height: s, borderRadius: s / 2, backgroundColor: color, marginHorizontal: s * 0.28 }, style]}
    />
  );
}

export const ThinkBubble = memo(function ThinkBubble({
  pose,
  w,
  size,
  color,
}: {
  pose: PoseSV;
  w: SharedValue<number>;
  size: number;
  color: string;
}) {
  const bw = Math.max(30, size * 0.3);
  const bh = bw * 0.52;
  const dot = bh * 0.22;
  const style = useAnimatedStyle(() => {
    const v = w.value;
    const float = Math.sin(pose.value.t * 1.6) * bh * 0.06;
    return {
      opacity: v,
      transform: [{ translateY: float + (1 - v) * bh * 0.4 }, { scale: 0.7 + 0.3 * v }],
    };
  });
  return (
    <Animated.View style={[styles.abs, { right: size * 0.02, top: size * 0.04, width: bw, height: bh * 1.6 }, style]}>
      <View style={[styles.bubble, { width: bw, height: bh, borderRadius: bh / 2 }]}>
        <Dot pose={pose} i={0} s={dot} color={color} />
        <Dot pose={pose} i={1} s={dot} color={color} />
        <Dot pose={pose} i={2} s={dot} color={color} />
      </View>
      <View style={[styles.trail, { width: bh * 0.3, height: bh * 0.3, borderRadius: bh, left: bw * 0.18, top: bh * 1.02 }]} />
      <View style={[styles.trail, { width: bh * 0.17, height: bh * 0.17, borderRadius: bh, left: bw * 0.08, top: bh * 1.36 }]} />
    </Animated.View>
  );
});

// ---------------------------------------------------------------------------
// Celebrate sparkles in brand colours
// ---------------------------------------------------------------------------

const SPARK_COLORS = ['#00B26F', '#3DD9B4', '#F5A524', '#FFFFFF', '#3DD9B4', '#F5A524', '#00B26F'];
/** Positions around the head (art units relative to the head centre). */
const SPARK_SPOTS: readonly [number, number][] = [
  [-118, -70],
  [-140, 10],
  [-100, 80],
  [120, -90],
  [150, -10],
  [108, 70],
  [0, -128],
];

const Star = memo(function Star({ s, color }: { s: number; color: string }) {
  return (
    <Svg width={s} height={s} viewBox="0 0 20 20">
      <Path d="M10 0 L12.4 7.6 L20 10 L12.4 12.4 L10 20 L7.6 12.4 L0 10 L7.6 7.6 Z" fill={color} />
    </Svg>
  );
});

function Spark({
  pose,
  w,
  i,
  x,
  y,
  s,
  k,
  color,
  reduced,
}: {
  pose: PoseSV;
  w: SharedValue<number>;
  i: number;
  x: number;
  y: number;
  s: number;
  k: number;
  color: string;
  reduced: boolean;
}) {
  const style = useAnimatedStyle(() => {
    const p = fract(pose.value.t * 0.65 + i / SPARK_SPOTS.length);
    const life = Math.sin(Math.PI * p);
    return {
      opacity: w.value * life,
      transform: [
        { translateY: reduced ? 0 : -p * 26 * k },
        { scale: 0.4 + 0.8 * life },
        { rotate: `${p * 120}deg` },
      ],
    };
  });
  return (
    <Animated.View style={[styles.abs, { left: x - s / 2, top: y - s / 2 }, style]}>
      <Star s={s} color={color} />
    </Animated.View>
  );
}

export function Sparkles({
  pose,
  w,
  center,
  k,
  reduced,
}: {
  pose: PoseSV;
  w: SharedValue<number>;
  center: [number, number];
  k: number;
  reduced: boolean;
}) {
  const s = Math.max(8, 22 * k);
  return (
    <>
      {SPARK_SPOTS.map(([dx, dy], i) => (
        <Spark
          key={i}
          pose={pose}
          w={w}
          i={i}
          x={center[0] + dx * k}
          y={center[1] + dy * k}
          s={i % 2 ? s * 0.7 : s}
          k={k}
          color={SPARK_COLORS[i % SPARK_COLORS.length]}
          reduced={reduced}
        />
      ))}
    </>
  );
}

const styles = StyleSheet.create({
  abs: { position: 'absolute' },
  ring: { position: 'absolute', left: 0, top: 0, borderWidth: 2 },
  bubble: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(234,246,240,0.95)',
  },
  trail: { position: 'absolute', backgroundColor: 'rgba(234,246,240,0.95)' },
});
