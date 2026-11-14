/**
 * Monthly stacked bars of the three baskets (fixed / irregular / leak).
 * The pedagogical centrepiece of Insights: users see which basket moves month to
 * month (usually leaks) while fixed costs stay flat. Tapping a month selects it
 * and reports it to the parent for a detail read-out.
 */
import { Pressable, View } from 'react-native';
import Svg, { G, Line, Rect, Text as SvgText } from 'react-native-svg';

import type { BasketKey, BasketMonth } from '@/api/types';
import { useT } from '@/i18n';
import { fontFamily, useTheme } from '@/theme';
import { niceMax, useEntrance, useWidth } from './useTween';

const ORDER: BasketKey[] = ['fixed', 'irregular', 'leak'];

type Props = { months: BasketMonth[]; height?: number; selected?: number; onSelect?: (i: number) => void };

export function StackedBasketBars({ months, height = 190, selected, onSelect }: Props) {
  const { c } = useTheme();
  const { month, compact } = useT();
  const [w, onLayout] = useWidth();
  const p = useEntrance(800, [months.map((m) => m.month + m.leak).join(',')]);
  const totals = months.map((m) => m.fixed + m.irregular + m.leak);
  const max = niceMax(Math.max(...totals, 1));
  const top = 18;
  const bottom = 22;
  const ch = height - top - bottom;
  const slot = months.length ? w / months.length : 0;
  const bw = Math.min(30, slot * 0.6);
  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          {[0.5, 1].map((g) => (
            <G key={g}>
              <Line x1={0} x2={w} y1={top + ch * (1 - g)} y2={top + ch * (1 - g)} stroke={c.chartGrid} />
              <SvgText x={w} y={top + ch * (1 - g) - 3} fontSize={12} fill={c.textFaint} textAnchor="end" fontFamily={fontFamily}>
                {compact(max * g)}
              </SvgText>
            </G>
          ))}
          {months.map((m, i) => {
            const x = i * slot + (slot - bw) / 2;
            let y = top + ch;
            const isSel = selected === undefined ? i === months.length - 1 : selected === i;
            return (
              <G key={m.month} opacity={isSel ? 1 : 0.55}>
                {ORDER.map((b, j) => {
                  const h = (m[b] / max) * ch * p;
                  y -= h;
                  const isTop = j === ORDER.length - 1;
                  return <Rect key={b} x={x} y={y} width={bw} height={Math.max(0, h - (isTop ? 0 : 1.5))} rx={isTop ? 6 : 2} fill={c.basket[b]} />;
                })}
                <SvgText x={x + bw / 2} y={height - 6} fontSize={12} fill={isSel ? c.text : c.textMuted} fontWeight={isSel ? '700' : '500'} textAnchor="middle" fontFamily={fontFamily}>
                  {month(m.month)}
                </SvgText>
              </G>
            );
          })}
        </Svg>
      ) : null}
      {onSelect && w > 0 ? (
        <View style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, flexDirection: 'row' }}>
          {months.map((m, i) => (
            <Pressable key={`hit-${m.month}`} style={{ flex: 1 }} onPress={() => onSelect(i)} accessibilityRole="button" accessibilityLabel={month(m.month)} />
          ))}
        </View>
      ) : null}
    </View>
  );
}
