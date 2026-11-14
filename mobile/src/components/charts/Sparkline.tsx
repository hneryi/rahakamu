/** Balance sparkline with gradient fill; draws in from left to right on mount. */
import { View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Path, Stop } from 'react-native-svg';

import { useEntrance, useWidth } from './useTween';

type Props = { values: number[]; height?: number; color: string; showZero?: boolean; zeroColor?: string };

export function Sparkline({ values, height = 56, color, showZero, zeroColor }: Props) {
  const [w, onLayout] = useWidth();
  const p = useEntrance(900, [values.length, values[values.length - 1]]);
  const n = values.length;
  let path = '';
  let area = '';
  let last = { x: 0, y: 0 };
  let zeroY: number | null = null;
  if (w > 0 && n > 1) {
    const min = Math.min(...values, showZero ? 0 : Infinity);
    const max = Math.max(...values);
    const span = max - min || 1;
    const pad = 4;
    const visible = Math.max(2, Math.ceil(n * p));
    const pts = values.slice(0, visible).map((v, i) => ({ x: (i / (n - 1)) * (w - pad * 2) + pad, y: pad + (1 - (v - min) / span) * (height - pad * 2) }));
    path = pts.map((pt, i) => `${i ? 'L' : 'M'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');
    area = `${path} L${pts[pts.length - 1].x.toFixed(1)},${height} L${pts[0].x.toFixed(1)},${height} Z`;
    last = pts[pts.length - 1];
    if (showZero && min < 0) zeroY = pad + (1 - (0 - min) / span) * (height - pad * 2);
  }
  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 && n > 1 ? (
        <Svg width={w} height={height}>
          <Defs>
            <LinearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={color} stopOpacity={0.35} />
              <Stop offset="1" stopColor={color} stopOpacity={0} />
            </LinearGradient>
          </Defs>
          {zeroY !== null ? <Path d={`M0,${zeroY} L${w},${zeroY}`} stroke={zeroColor ?? '#FF6B5A'} strokeDasharray="4 4" strokeWidth={1} /> : null}
          <Path d={area} fill="url(#spark)" />
          <Path d={path} stroke={color} strokeWidth={2.4} fill="none" strokeLinejoin="round" strokeLinecap="round" />
          <Circle cx={last.x} cy={last.y} r={4} fill={color} />
          <Circle cx={last.x} cy={last.y} r={8} fill={color} opacity={0.2} />
        </Svg>
      ) : null}
    </View>
  );
}
