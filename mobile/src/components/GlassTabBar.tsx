/**
 * Floating glass tab bar (SPEC §5.4) for the headless `expo-router/ui` Tabs.
 *
 * A blurred pill hovering above the content with a spring-animated active
 * indicator. Using headless tabs (instead of the platform tab bar) gives an
 * identical look on iOS, Android and web — important because the web build is
 * what S-mobiili would embed first.
 */
import { BlurView } from 'expo-blur';
import { forwardRef, type ComponentRef, type ReactNode } from 'react';
import { Platform, Pressable, View, type ViewProps } from 'react-native';
import type { TabTriggerSlotProps } from 'expo-router/ui';
import Animated, { useAnimatedStyle, withSpring } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Icon, type IconName } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { haptic } from '@/lib/haptics';
import { layout, makeStyles, springs, useTheme } from '@/theme';

export const GlassTabBar = forwardRef<ComponentRef<typeof View>, ViewProps & { children?: ReactNode }>(function GlassTabBar({ children, style, ...rest }, ref) {
  const s = useStyles();
  const { name } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View ref={ref} {...rest} pointerEvents="box-none" style={[s.wrap, { bottom: Math.max(insets.bottom, 10) + 2 }, style]}>
      <View style={s.bar}>
        {Platform.OS === 'android' ? null : <BlurView intensity={40} tint={name === 'dark' ? 'dark' : 'light'} style={s.blur} />}
        <View style={s.fallback} />
        <View style={s.items}>{children}</View>
      </View>
    </View>
  );
});

type TabButtonProps = TabTriggerSlotProps & { icon: IconName; label: string; tid?: string };

export const TabButton = forwardRef<ComponentRef<typeof View>, TabButtonProps>(function TabButton({ icon, label, isFocused, onPress, tid, ...rest }, ref) {
  const s = useStyles();
  const { c } = useTheme();
  const pill = useAnimatedStyle(() => ({
    opacity: withSpring(isFocused ? 1 : 0, springs.snappy),
    transform: [{ scale: withSpring(isFocused ? 1 : 0.6, springs.snappy) }],
  }));
  return (
    <Pressable
      ref={ref}
      {...rest}
      testID={tid}
      onPress={(e) => {
        if (!isFocused) haptic.tap();
        onPress?.(e);
      }}
      accessibilityRole="tab"
      accessibilityState={{ selected: !!isFocused }}
      accessibilityLabel={label}
      style={s.tab}
    >
      <Animated.View style={[s.pill, pill]} />
      <Icon name={icon} size={21} color={isFocused ? c.primary : c.textMuted} fill={isFocused ? `${c.primary}33` : 'none'} />
      <Text variant="micro" weight={isFocused ? '800' : '600'} color={isFocused ? c.text : c.textMuted} numberOfLines={1}>
        {label}
      </Text>
    </Pressable>
  );
});

const useStyles = makeStyles((t) => ({
  wrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center', paddingHorizontal: layout.gutter },
  bar: {
    width: '100%',
    maxWidth: layout.maxWidth - layout.gutter * 2,
    height: layout.tabBarHeight,
    borderRadius: t.radius.pill,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: t.c.border,
    shadowColor: '#000',
    shadowOpacity: 0.35,
    shadowRadius: 20,
    shadowOffset: { width: 0, height: 10 },
    elevation: 12,
  },
  blur: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 },
  fallback: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: Platform.OS === 'android' ? t.c.glassFallback : t.name === 'dark' ? 'rgba(12,30,22,0.72)' : 'rgba(255,255,255,0.75)' },
  items: { flex: 1, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 6 },
  tab: { flex: 1, height: layout.tabBarHeight - 12, alignItems: 'center', justifyContent: 'center', gap: 2, borderRadius: t.radius.pill },
  pill: { position: 'absolute', left: 4, right: 4, top: 0, bottom: 0, borderRadius: t.radius.pill, backgroundColor: `${t.c.primary}1F` },
}));
