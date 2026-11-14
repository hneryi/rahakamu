/** Thin animated progress bar (0..1). */
import { useEffect } from 'react';
import { View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

import { springs, useTheme } from '@/theme';

export function ProgressBar({ value, color, height = 6 }: { value: number; color?: string; height?: number }) {
  const { c } = useTheme();
  const v = useSharedValue(0);
  useEffect(() => {
    v.set(withSpring(Math.max(0, Math.min(1, value)), springs.gentle));
  }, [value, v]);
  const a = useAnimatedStyle(() => ({ width: `${v.get() * 100}%` }));
  return (
    <View style={{ height, borderRadius: height, backgroundColor: c.surfaceStrong, overflow: 'hidden' }}>
      <Animated.View style={[{ height, borderRadius: height, backgroundColor: color ?? c.primary }, a]} />
    </View>
  );
}
