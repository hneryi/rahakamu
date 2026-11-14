/** Circular progress ring (goals). Animates from 0 to `progress`; children render centred. */
import type { ReactNode } from 'react';
import { View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';

import { useTheme } from '@/theme';
import { useTween } from './useTween';

type Props = { progress: number; size?: number; stroke?: number; color: string; track?: string; children?: ReactNode };

export function ProgressRing({ progress, size = 64, stroke = 7, color, track, children }: Props) {
  const { c } = useTheme();
  const v = useTween(Math.max(0, Math.min(1, progress)), 900);
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }} accessibilityRole="progressbar" accessibilityValue={{ min: 0, max: 100, now: Math.round(progress * 100) }}>
      <Svg width={size} height={size} style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}>
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={track ?? c.surfaceStrong} strokeWidth={stroke} fill="none" />
        <Circle cx={size / 2} cy={size / 2} r={r} stroke={color} strokeWidth={stroke} fill="none" strokeLinecap="round" strokeDasharray={`${circ} ${circ}`} strokeDashoffset={circ * (1 - v)} />
      </Svg>
      {children}
    </View>
  );
}
