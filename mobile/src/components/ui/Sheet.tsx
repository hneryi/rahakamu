/**
 * Bottom sheet built on RN `Modal` + Reanimated (no extra dependency).
 *
 * Springs up on open, slides down and fades on close (we keep the Modal mounted
 * until the exit animation completes). Keyboard-aware so form sheets (create
 * goal) keep the focused field visible. Constrained to the 480 px app column on
 * web so it lines up with the phone frame.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring, withTiming } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { scheduleOnRN } from 'react-native-worklets';

import { layout, makeStyles, springs, useTheme } from '@/theme';
import { Icon } from './Icon';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

type Props = { visible: boolean; onClose: () => void; title?: string; children: ReactNode; footer?: ReactNode };

export function Sheet({ visible, onClose, title, children, footer }: Props) {
  const s = useStyles();
  const { c } = useTheme();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(visible);
  // Mount immediately when opened (derived state update during render is the
  // React-recommended pattern); unmount only after the exit animation.
  if (visible && !mounted) setMounted(true);
  const p = useSharedValue(0);

  useEffect(() => {
    if (visible) {
      p.set(withSpring(1, springs.snappy));
    } else {
      p.set(
        withTiming(0, { duration: 200 }, (finished) => {
          if (finished) scheduleOnRN(setMounted, false);
        }),
      );
    }
  }, [visible, p]);

  const backdrop = useAnimatedStyle(() => ({ opacity: p.get() }));
  const sheet = useAnimatedStyle(() => ({ transform: [{ translateY: (1 - p.get()) * 600 }] }));

  if (!mounted) return null;
  return (
    <Modal transparent visible={mounted} onRequestClose={onClose} animationType="none" statusBarTranslucent navigationBarTranslucent>
      <KeyboardAvoidingView style={s.fill} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <Animated.View style={[StyleSheet.absoluteFill, { backgroundColor: c.overlay }, backdrop]}>
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} accessibilityLabel="Close" />
        </Animated.View>
        <View style={s.column} pointerEvents="box-none">
          <Animated.View style={[s.sheet, { paddingBottom: insets.bottom + 16 }, sheet]}>
            <View style={s.handle} />
            <View style={s.header}>
              <Text variant="title" style={s.title} numberOfLines={2}>
                {title}
              </Text>
              <PressableScale onPress={onClose} style={s.close} accessibilityLabel="Close">
                <Icon name="close" size={18} color={c.textMuted} />
              </PressableScale>
            </View>
            <ScrollView style={s.scroll} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
              {children}
            </ScrollView>
            {footer ? <View style={s.footer}>{footer}</View> : null}
          </Animated.View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const useStyles = makeStyles((t) => ({
  fill: { flex: 1, justifyContent: 'flex-end' },
  column: { width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', flex: 1, justifyContent: 'flex-end' },
  sheet: {
    maxHeight: '92%',
    backgroundColor: t.name === 'dark' ? '#0E2219' : '#FFFFFF',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    borderWidth: 1,
    borderColor: t.c.border,
    paddingTop: 8,
  },
  handle: { alignSelf: 'center', width: 40, height: 5, borderRadius: 3, backgroundColor: t.c.surfaceStrong, marginBottom: 8 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingBottom: 8, gap: 12 },
  title: { flex: 1 },
  close: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surface },
  scroll: { flexGrow: 0 },
  body: { paddingHorizontal: 20, paddingBottom: 12, gap: 14 },
  footer: { paddingHorizontal: 20, paddingTop: 8 },
}));
