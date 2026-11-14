/** Global toast stack (top of screen). Fed by `useUi().showToast` / `toast()`. */
import { View } from 'react-native';
import Animated, { FadeInUp, FadeOutUp, LinearTransition } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useUi } from '@/store/ui';
import { layout, makeStyles, useTheme } from '@/theme';
import { Icon } from './Icon';
import { Text } from './Text';

export function Toasts() {
  const toasts = useUi((s) => s.toasts);
  const dismiss = useUi((s) => s.dismissToast);
  const insets = useSafeAreaInsets();
  const s = useStyles();
  const { c } = useTheme();
  return (
    <View pointerEvents="box-none" style={[s.wrap, { top: insets.top + 8 }]}>
      {toasts.map((t) => (
        <Animated.View key={t.id} entering={FadeInUp.springify().damping(16)} exiting={FadeOutUp} layout={LinearTransition} style={s.toast}>
          <Icon name={t.tone === 'good' ? 'check' : t.tone === 'warn' ? 'info' : 'sparkle'} size={16} color={t.tone === 'good' ? c.good : t.tone === 'warn' ? c.warn : c.accent} />
          <Text variant="caption" weight="600" style={{ flex: 1 }} onPress={() => dismiss(t.id)}>
            {t.text}
          </Text>
        </Animated.View>
      ))}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { position: 'absolute', left: 0, right: 0, alignItems: 'center', gap: 8, paddingHorizontal: 16, zIndex: 1000 },
  toast: {
    width: '100%',
    maxWidth: layout.maxWidth - 32,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 18,
    backgroundColor: t.name === 'dark' ? 'rgba(18,40,30,0.97)' : 'rgba(255,255,255,0.98)',
    borderWidth: 1,
    borderColor: t.c.border,
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
}));
