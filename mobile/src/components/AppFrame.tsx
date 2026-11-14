/**
 * Desktop-web presentation frame.
 *
 * On phones (native or narrow browsers) this is a pass-through. On wide browser
 * windows the app is rendered in a centred, phone-proportioned column (max 480 px)
 * with rounded corners, so the UX reads as a mobile app during demos instead
 * of a stretched website. A small caption explains what the viewer is seeing.
 */
import type { ReactNode } from 'react';
import { Platform, StyleSheet, useWindowDimensions, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';

import { Text } from '@/components/ui/Text';
import { layout } from '@/theme';

export function AppFrame({ children }: { children: ReactNode }) {
  const { width, height } = useWindowDimensions();
  const framed = Platform.OS === 'web' && width >= 720 && height >= 640;
  if (!framed) return <View style={{ flex: 1 }}>{children}</View>;
  const frameH = Math.min(height - 48, 900);
  return (
    <View style={styles.backdrop}>
      <LinearGradient colors={['#03100B', '#0A2218', '#03100B']} style={StyleSheet.absoluteFill} />
      {width >= 1180 ? (
      <View style={styles.side}>
        <Text variant="hero" weight="800" color="#F2F7F4">
          Rahakamu
        </Text>
        <Text variant="callout" color="#9FB3A9" style={{ maxWidth: 260 }}>
          Personal Economic Trainer — talk with your own money. Junction 2026 hackathon project. Not an official S-Pankki product.
        </Text>
      </View>
      ) : null}
      <View style={[styles.frame, { height: frameH }]}>{children}</View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  side: { position: 'absolute', left: 48, top: 48, gap: 8 },
  frame: {
    width: layout.maxWidth,
    maxWidth: '100%',
    borderRadius: 40,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.10)',
    shadowColor: '#000',
    shadowOpacity: 0.6,
    shadowRadius: 60,
    shadowOffset: { width: 0, height: 30 },
  },
});
