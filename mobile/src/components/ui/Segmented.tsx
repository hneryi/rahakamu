/** Segmented control with a sliding spring indicator (period selector, theme, language). */
import { useState } from 'react';
import { View, type LayoutChangeEvent } from 'react-native';
import Animated, { useAnimatedStyle, withSpring } from 'react-native-reanimated';

import { haptic } from '@/lib/haptics';
import { makeStyles, springs, useTheme } from '@/theme';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

type Props<T extends string | number> = { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; color?: string; testIDPrefix?: string };

export function Segmented<T extends string | number>({ options, value, onChange, color, testIDPrefix }: Props<T>) {
  const s = useStyles();
  const { c } = useTheme();
  const [w, setW] = useState(0);
  const idx = Math.max(0, options.findIndex((o) => o.value === value));
  const segW = w > 0 ? (w - 8) / options.length : 0;
  const indicator = useAnimatedStyle(() => ({ width: segW, transform: [{ translateX: withSpring(idx * segW, springs.snappy) }] }), [idx, segW]);
  return (
    <View style={s.wrap} onLayout={(e: LayoutChangeEvent) => setW(e.nativeEvent.layout.width)} accessibilityRole="tablist">
      {w > 0 ? <Animated.View style={[s.indicator, { backgroundColor: color ? `${color}33` : c.surfaceStrong }, indicator]} /> : null}
      {options.map((o) => {
        const active = o.value === value;
        return (
          <PressableScale
            key={String(o.value)}
            testID={testIDPrefix ? `${testIDPrefix}-${o.value}` : undefined}
            hapticOnPress={false}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            onPress={() => {
              if (!active) {
                haptic.tap();
                onChange(o.value);
              }
            }}
            style={s.seg}
          >
            <Text variant="caption" weight={active ? '700' : '500'} color={active ? (color ?? c.text) : c.textMuted} numberOfLines={1}>
              {o.label}
            </Text>
          </PressableScale>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { flexDirection: 'row', padding: 4, borderRadius: t.radius.pill, backgroundColor: t.c.surface, borderWidth: 1, borderColor: t.c.border },
  indicator: { position: 'absolute', top: 4, bottom: 4, left: 4, borderRadius: t.radius.pill },
  seg: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 8, minHeight: 36 },
}));
