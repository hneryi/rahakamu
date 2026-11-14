/** Donut chart with animated sweep, centre total and a compact legend. */
import { View } from 'react-native';
import Svg, { Circle, G } from 'react-native-svg';

import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { useTheme } from '@/theme';
import { useEntrance } from './useTween';

export type Slice = { label: string; value: number; color?: string };

const FALLBACK = ['#00B26F', '#5B8DEF', '#F5A524', '#FF6B8A', '#3DD9B4', '#A78BFA', '#F97316', '#94A3B8'];

type Props = { slices: Slice[]; size?: number; unit?: string; centerLabel?: string; legend?: boolean };

export function DonutChart({ slices, size = 150, unit = '€', centerLabel, legend = true }: Props) {
  const { c } = useTheme();
  const { money, num, pct } = useT();
  const p = useEntrance(900, [slices.map((s) => s.value).join(',')]);
  const total = slices.reduce((a, s) => a + Math.max(0, s.value), 0) || 1;
  const stroke = size * 0.15;
  const r = (size - stroke) / 2;
  const circ = 2 * Math.PI * r;
  const gap = slices.length > 1 ? 2 : 0;
  // Cumulative start fraction of each slice (computed up-front; render stays pure).
  const starts = slices.map((_, i) => slices.slice(0, i).reduce((a, x) => a + Math.max(0, x.value), 0) / total);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: legend ? 'flex-start' : 'center', gap: 16, flexWrap: 'wrap' }}>
      <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={size} height={size} style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}>
          <G>
            <Circle cx={size / 2} cy={size / 2} r={r} stroke={c.surfaceStrong} strokeWidth={stroke} fill="none" />
            {slices.map((s, i) => {
              const frac = Math.max(0, s.value) / total;
              const len = Math.max(0, frac * circ * p - gap);
              const offset = -starts[i] * circ * p;
              return (
                <Circle
                  key={`${s.label}-${i}`}
                  cx={size / 2}
                  cy={size / 2}
                  r={r}
                  stroke={s.color ?? FALLBACK[i % FALLBACK.length]}
                  strokeWidth={stroke}
                  fill="none"
                  strokeDasharray={`${len} ${circ}`}
                  strokeDashoffset={offset}
                />
              );
            })}
          </G>
        </Svg>
        <Text variant="caption" weight="800" money align="center">
          {unit === '€' ? money(total) : `${num(total)}${unit}`}
        </Text>
        {centerLabel ? (
          <Text variant="micro" tone="muted" align="center" numberOfLines={2} style={{ maxWidth: size - stroke * 2 - 16 }}>
            {centerLabel}
          </Text>
        ) : null}
      </View>
      {legend ? (
        <View style={{ flex: 1, minWidth: 140, gap: 7 }}>
          {slices.map((s, i) => (
            <View key={`${s.label}-${i}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: s.color ?? FALLBACK[i % FALLBACK.length] }} />
              <Text variant="caption" numberOfLines={1} style={{ flex: 1 }}>
                {s.label}
              </Text>
              <Text variant="caption" tone="muted" money>
                {pct(Math.max(0, s.value) / total)}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}
