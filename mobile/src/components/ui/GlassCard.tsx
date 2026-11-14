/**
 * The basic surface of the app: translucent "glass" fill, 1 px hairline border,
 * radius 24 (SPEC §5.4). Optionally pressable, optionally tinted with an accent
 * glow (used for the safe-to-spend status and persona-coloured cards).
 */
import type { ReactNode } from 'react';
import { View, type StyleProp, type ViewStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { makeStyles, useTheme } from '@/theme';
import { PressableScale } from './PressableScale';

type Props = {
  children?: ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  tint?: string;
  padded?: boolean;
  accessibilityLabel?: string;
  testID?: string;
};

export function GlassCard({ children, style, onPress, tint, padded = true, accessibilityLabel, testID }: Props) {
  const s = useStyles();
  const content = (
    <>
      {tint ? (
        <LinearGradient
          colors={[`${tint}2E`, `${tint}05`]}
          start={{ x: 0, y: 0 }}
          end={{ x: 1, y: 1 }}
          style={[StyleSheetAbsolute, { borderRadius: 24 }]}
          pointerEvents="none"
        />
      ) : null}
      {children}
    </>
  );
  if (onPress) {
    return (
      <PressableScale testID={testID} onPress={onPress} style={[s.card, padded && s.padded, style]} accessibilityLabel={accessibilityLabel}>
        {content}
      </PressableScale>
    );
  }
  return (
    <View testID={testID} style={[s.card, padded && s.padded, style]}>
      {content}
    </View>
  );
}

const StyleSheetAbsolute = { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 } as const;

const useStyles = makeStyles((t) => ({
  card: {
    backgroundColor: t.c.surface,
    borderColor: t.c.border,
    borderWidth: 1,
    borderRadius: t.radius.lg,
    overflow: 'hidden',
  },
  padded: { padding: t.space.md },
}));

export function Divider() {
  const { c } = useTheme();
  return <View style={{ height: 1, backgroundColor: c.border, marginVertical: 12 }} />;
}
