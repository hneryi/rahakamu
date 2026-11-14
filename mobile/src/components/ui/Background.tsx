/**
 * Screen background: the spec's deep-green vertical gradient plus two soft
 * radial "glows" (primary green and the active persona's colour) that give the
 * glass surfaces something to refract. Pure gradients — no images to load.
 */
import { LinearGradient } from 'expo-linear-gradient';
import { StyleSheet, View } from 'react-native';
import Svg, { Defs, RadialGradient, Rect, Stop } from 'react-native-svg';

import { personaColor, useTheme } from '@/theme';
import { useSession } from '@/store/session';

export function Background() {
  const { c, name } = useTheme();
  const persona = useSession((s) => s.persona);
  const glow = personaColor[persona];
  const o = name === 'dark' ? 0.22 : 0.14;
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <LinearGradient colors={c.bg} style={StyleSheet.absoluteFill} />
      <Svg style={StyleSheet.absoluteFill} width="100%" height="100%" preserveAspectRatio="none">
        <Defs>
          <RadialGradient id="g1" cx="12%" cy="4%" rx="70%" ry="38%">
            <Stop offset="0" stopColor={c.primary} stopOpacity={o} />
            <Stop offset="1" stopColor={c.primary} stopOpacity={0} />
          </RadialGradient>
          <RadialGradient id="g2" cx="95%" cy="88%" rx="65%" ry="35%">
            <Stop offset="0" stopColor={glow} stopOpacity={o * 0.7} />
            <Stop offset="1" stopColor={glow} stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Rect x="0" y="0" width="100%" height="100%" fill="url(#g1)" />
        <Rect x="0" y="0" width="100%" height="100%" fill="url(#g2)" />
      </Svg>
    </View>
  );
}
