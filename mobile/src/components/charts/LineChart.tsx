/**
 * Line chart with gradient area, optional dashed target line (e.g. goal amount)
 * and min/max annotations. Draws from left to right on mount.
 */
import { View } from 'react-native';
import Svg, { Circle, Defs, G, Line, LinearGradient, Path, Stop, Text as SvgText } from 'react-native-svg';

import { useT } from '@/i18n';
import { fontFamily, useTheme } from '@/theme';
import { useEntrance, useWidth } from './useTween';

type Props = { points: { x: string; y: number }[]; target?: number; unit?: string; height?: number; color?: string };

export function LineChart({ points, target, unit = '€', height = 170, color }: Props) {
  const { c } = useTheme();
  const { compact } = useT();
  const [w, onLayout] = useWidth();
  const p = useEntrance(900, [points.length, points[points.length - 1]?.y]);
  const stroke = color ?? c.accent;
  const n = points.length;
  const left = 40;
  const right = 10;
  const top = 16;
  const bottom = 22;
  if (n < 2) return <View style={{ height }} />;
  const ys = points.map((pt) => pt.y);
  const min = Math.min(...ys, target ?? Infinity);
  const max = Math.max(...ys, target ?? -Infinity);
  const lo = min === max ? min - 1 : min - (max - min) * 0.08;
  const hi = min === max ? max + 1 : max + (max - min) * 0.08;
  const cw = Math.max(0, w - left - right);
  const ch = height - top - bottom;
  const X = (i: number) => left + (i / (n - 1)) * cw;
  const Y = (v: number) => top + (1 - (v - lo) / (hi - lo)) * ch;
  const visible = Math.max(2, Math.ceil(n * p));
  const pts = points.slice(0, visible);
  const path = pts.map((pt, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(pt.y).toFixed(1)}`).join(' ');
  const area = `${path} L${X(visible - 1).toFixed(1)},${top + ch} L${left},${top + ch} Z`;
  const labelIdx = n <= 6 ? points.map((_, i) => i) : [0, Math.floor((n - 1) / 2), n - 1];
  const suffix = unit === '€' ? ' €' : unit;
  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          <Defs>
            <LinearGradient id="lc" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={stroke} stopOpacity={0.3} />
              <Stop offset="1" stopColor={stroke} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          {[lo + (hi - lo) * 0.15, (lo + hi) / 2, hi - (hi - lo) * 0.1].map((v, i) => (
            <G key={i}>
              <Line x1={left} x2={w - right} y1={Y(v)} y2={Y(v)} stroke={c.chartGrid} strokeWidth={1} />
              <SvgText x={left - 6} y={Y(v) + 3.5} fontSize={12} fill={c.textFaint} textAnchor="end" fontFamily={fontFamily}>
                {compact(v)}
              </SvgText>
            </G>
          ))}
          {target !== undefined ? (
            <>
              <Line x1={left} x2={w - right} y1={Y(target)} y2={Y(target)} stroke={c.amber} strokeWidth={1.5} strokeDasharray="5 5" />
              <SvgText x={w - right} y={Y(target) - 5} fontSize={12} fontWeight="700" fill={c.amber} textAnchor="end" fontFamily={fontFamily}>
                {`${compact(target)}${suffix}`}
              </SvgText>
            </>
          ) : null}
          <Path d={area} fill="url(#lc)" />
          <Path d={path} stroke={stroke} strokeWidth={2.5} fill="none" strokeLinejoin="round" strokeLinecap="round" />
          <Circle cx={X(visible - 1)} cy={Y(pts[visible - 1].y)} r={4.5} fill={stroke} />
          {labelIdx.map((i) => (
            <SvgText key={i} x={X(i)} y={height - 6} fontSize={12} fill={c.textMuted} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} fontFamily={fontFamily}>
              {points[i].x}
            </SvgText>
          ))}
        </Svg>
      ) : null}
    </View>
  );
}
