/**
 * Slider built with react-native-gesture-handler v3 hooks + Reanimated —
 * no extra dependency. The thumb follows the finger on the UI thread (smooth even
 * while the JS thread renders the what-if result); the stepped value is sent to
 * JS only when it actually changes. Tap anywhere on the track to jump.
 */
import { useEffect } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import { GestureDetector, usePanGesture } from 'react-native-gesture-handler';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { scheduleOnRN } from 'react-native-worklets';

import { haptic } from '@/lib/haptics';
import { springs, useTheme } from '@/theme';

type Props = {
  min: number;
  max: number;
  step?: number;
  value: number;
  onChange: (v: number) => void;
  onCommit?: (v: number) => void;
  color?: string;
  accessibilityLabel?: string;
};

const THUMB = 26;

export function Slider({ min, max, step = 1, value, onChange, onCommit, color, accessibilityLabel }: Props) {
  const { c } = useTheme();
  const accent = color ?? c.primary;
  const width = useSharedValue(0);
  const ratio = useSharedValue(max === min ? 0 : (value - min) / (max - min));
  const last = useSharedValue(value);
  const active = useSharedValue(0);

  useEffect(() => {
    // External value changes (e.g. new widget data) move the thumb.
    if (active.get() === 0 && max !== min) {
      ratio.set(withSpring((value - min) / (max - min), springs.snappy));
      last.set(value);
    }
  }, [value, min, max, ratio, last, active]);

  const emit = (v: number) => {
    haptic.tap();
    onChange(v);
  };
  const commit = (v: number) => onCommit?.(v);

  const pan = usePanGesture({
    minDistance: 0,
    onBegin: (e) => {
      'worklet';
      active.set(1);
      const w = width.get() || 1;
      const r = Math.min(1, Math.max(0, (e.x - THUMB / 2) / Math.max(1, w - THUMB)));
      ratio.set(r);
      const v = Math.round((min + r * (max - min)) / step) * step;
      if (v !== last.get()) {
        last.set(v);
        scheduleOnRN(emit, v);
      }
    },
    onUpdate: (e) => {
      'worklet';
      const w = width.get() || 1;
      const r = Math.min(1, Math.max(0, (e.x - THUMB / 2) / Math.max(1, w - THUMB)));
      ratio.set(r);
      const v = Math.round((min + r * (max - min)) / step) * step;
      if (v !== last.get()) {
        last.set(v);
        scheduleOnRN(emit, v);
      }
    },
    onFinalize: () => {
      'worklet';
      active.set(0);
      scheduleOnRN(commit, last.get());
    },
  });

  const thumb = useAnimatedStyle(() => ({
    transform: [{ translateX: ratio.get() * Math.max(0, width.get() - THUMB) }, { scale: withSpring(active.get() ? 1.15 : 1, springs.snappy) }],
  }));
  const fill = useAnimatedStyle(() => ({ width: ratio.get() * Math.max(0, width.get() - THUMB) + THUMB / 2 }));

  const onLayout = (e: LayoutChangeEvent) => {
    width.set(e.nativeEvent.layout.width);
  };

  return (
    <GestureDetector gesture={pan}>
      <View
        onLayout={onLayout}
        style={{ height: 44, justifyContent: 'center' }}
        accessible
        accessibilityRole="adjustable"
        accessibilityLabel={accessibilityLabel}
        accessibilityValue={{ min, max, now: value }}
        accessibilityActions={[{ name: 'increment' }, { name: 'decrement' }]}
        onAccessibilityAction={(e) => {
          const next = e.nativeEvent.actionName === 'increment' ? Math.min(max, value + step * 5) : Math.max(min, value - step * 5);
          onChange(next);
          onCommit?.(next);
        }}
      >
        <View style={{ height: 8, borderRadius: 4, backgroundColor: c.surfaceStrong, marginHorizontal: 0 }} />
        <Animated.View style={[{ position: 'absolute', left: 0, height: 8, borderRadius: 4, backgroundColor: accent }, fill]} />
        <Animated.View
          style={[
            {
              position: 'absolute',
              left: 0,
              width: THUMB,
              height: THUMB,
              borderRadius: THUMB / 2,
              backgroundColor: '#FFFFFF',
              borderWidth: 3,
              borderColor: accent,
              shadowColor: '#000',
              shadowOpacity: 0.3,
              shadowRadius: 6,
              shadowOffset: { width: 0, height: 2 },
              elevation: 4,
            },
            thumb,
          ]}
        />
      </View>
    </GestureDetector>
  );
}
