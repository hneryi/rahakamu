/** Pulsing placeholder shown while data loads — keeps layout stable (no jumps). */
import { useEffect } from 'react';
import type { DimensionValue, StyleProp, ViewStyle } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import { useTheme } from '@/theme';

export function Skeleton({ height = 16, width = '100%', radius = 10, style }: { height?: number; width?: DimensionValue; radius?: number; style?: StyleProp<ViewStyle> }) {
  const { c } = useTheme();
  const o = useSharedValue(0.45);
  useEffect(() => {
    o.set(withRepeat(withTiming(1, { duration: 850 }), -1, true));
  }, [o]);
  const a = useAnimatedStyle(() => ({ opacity: o.get() }));
  return <Animated.View style={[{ height, width, borderRadius: radius, backgroundColor: c.surfaceStrong }, a, style]} />;
}
