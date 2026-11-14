/**
 * Bar chart. Vertical columns for short labels (months, weekdays); switches to a
 * horizontal ranked list when labels are long (merchants, subscriptions) because
 * rotated axis labels are unreadable on a phone.
 */
import { Pressable, View } from 'react-native';
import Svg, { G, Line, Rect, Text as SvgText } from 'react-native-svg';

import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { fontFamily, useTheme } from '@/theme';
import { niceMax, useEntrance, useWidth } from './useTween';

export type Bar = { label: string; value: number; highlight?: boolean; color?: string };

type Props = { bars: Bar[]; unit?: string; height?: number; color?: string; formatLabel?: (l: string) => string; onPressBar?: (b: Bar, i: number) => void };

export function BarChart({ bars, unit = '€', height = 160, color, formatLabel, onPressBar }: Props) {
  const longLabels = bars.some((b) => (formatLabel ? formatLabel(b.label) : b.label).length > 8) || bars.length > 8;
  return longLabels ? <HBars bars={bars} unit={unit} color={color} formatLabel={formatLabel} onPressBar={onPressBar} /> : <VBars bars={bars} unit={unit} height={height} color={color} formatLabel={formatLabel} onPressBar={onPressBar} />;
}

function VBars({ bars, unit, height, color, formatLabel, onPressBar }: Required<Pick<Props, 'unit' | 'height'>> & Props) {
  const { c } = useTheme();
  const { compact } = useT();
  const [w, onLayout] = useWidth();
  const p = useEntrance(700, [bars.map((b) => b.value).join(',')]);
  const max = niceMax(Math.max(...bars.map((b) => b.value), 1));
  const top = 20;
  const bottom = 22;
  const chartH = height - top - bottom;
  const slot = bars.length ? w / bars.length : 0;
  const bw = Math.min(34, slot * 0.58);
  const anyHighlight = bars.some((b) => b.highlight);
  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          {[0.5, 1].map((g) => (
            <Line key={g} x1={0} x2={w} y1={top + chartH * (1 - g)} y2={top + chartH * (1 - g)} stroke={c.chartGrid} strokeWidth={1} />
          ))}
          <Line x1={0} x2={w} y1={top + chartH} y2={top + chartH} stroke={c.border} strokeWidth={1} />
          {bars.map((b, i) => {
            const h = Math.max(2, (b.value / max) * chartH * p);
            const x = i * slot + (slot - bw) / 2;
            const fill = b.color ?? (b.highlight || !anyHighlight ? (color ?? c.primary) : `${color ?? c.primary}66`);
            const showVal = b.highlight || bars.length <= 6;
            return (
              <G key={`${b.label}-${i}`}>
                <Rect x={x} y={top + chartH - h} width={bw} height={h} rx={Math.min(8, bw / 2.5)} fill={fill} />
                {showVal ? (
                  <SvgText x={x + bw / 2} y={top + chartH - h - 5} fontSize={12} fontWeight="700" fill={b.highlight ? c.text : c.textMuted} textAnchor="middle" fontFamily={fontFamily}>
                    {`${compact(b.value)}${unit === '€' ? '' : unit}`}
                  </SvgText>
                ) : null}
                <SvgText x={x + bw / 2} y={height - 6} fontSize={12} fill={b.highlight ? c.text : c.textMuted} textAnchor="middle" fontWeight={b.highlight ? '700' : '500'} fontFamily={fontFamily}>
                  {formatLabel ? formatLabel(b.label) : b.label}
                </SvgText>
              </G>
            );
          })}
        </Svg>
      ) : null}
      {onPressBar && w > 0 ? (
        <View style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, flexDirection: 'row' }}>
          {bars.map((b, i) => (
            <Pressable key={`hit-${b.label}-${i}`} style={{ flex: 1 }} onPress={() => onPressBar(b, i)} accessibilityRole="button" accessibilityLabel={`${b.label} ${b.value}`} />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function HBars({ bars, unit, color, formatLabel, onPressBar }: Props) {
  const { c } = useTheme();
  const { money, num } = useT();
  const p = useEntrance(700, [bars.length]);
  const max = Math.max(...bars.map((b) => b.value), 1);
  return (
    <View style={{ gap: 10 }}>
      {bars.map((b, i) => (
        <Pressable key={`${b.label}-${i}`} style={{ gap: 4 }} disabled={!onPressBar} onPress={onPressBar ? () => onPressBar(b, i) : undefined} accessibilityRole={onPressBar ? 'button' : undefined} accessibilityLabel={`${formatLabel ? formatLabel(b.label) : b.label} ${Math.round(b.value)}`}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
            <Text variant="caption" weight={b.highlight ? '700' : '500'} numberOfLines={1} style={{ flex: 1 }}>
              {formatLabel ? formatLabel(b.label) : b.label}
            </Text>
            <Text variant="caption" weight="700" money>
              {unit === '€' ? money(b.value) : `${num(b.value, 1)}${unit ?? ''}`}
            </Text>
          </View>
          <View style={{ height: 8, borderRadius: 4, backgroundColor: c.surfaceStrong, overflow: 'hidden' }}>
            <View style={{ height: 8, borderRadius: 4, width: `${(b.value / max) * 100 * p}%`, backgroundColor: b.color ?? (b.highlight ? c.amber : (color ?? c.primary)) }} />
          </View>
        </Pressable>
      ))}
    </View>
  );
}
