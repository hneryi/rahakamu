/**
 * Microphone: hold to talk (release sends), or tap once to start and tap again
 * to send — the recogniser also ends by itself after a pause. While live the
 * character switches to "listening" (via `onListeningChange`), a pulsing ring
 * shows the mic is on and interim words stream to `onTranscript`. Pressing the
 * mic stops any read-aloud first. If recognition is unavailable or the mic is
 * refused, we toast and hand focus to the keyboard.
 */
import { useEffect, useRef } from 'react';
import { View } from 'react-native';
import Animated, { cancelAnimation, useAnimatedStyle, useSharedValue, withRepeat, withTiming } from 'react-native-reanimated';

import type { Locale } from '@/api/types';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { stopSpeaking } from '@/hooks/useSpeech';
import { useVoiceInput, type VoiceError } from '@/hooks/useVoiceInput';
import { useT, type TKey } from '@/i18n';
import { haptic } from '@/lib/haptics';
import { toast } from '@/store/ui';
import { useTheme } from '@/theme';
import { useVoiceLang } from './VoiceLangPill';

type Props = {
  onFinal: (text: string, lang: Locale) => void;
  onListeningChange?: (listening: boolean) => void;
  onTranscript?: (partial: string) => void;
  onUnavailable?: () => void;
  size?: number;
  color?: string;
};

const ERR: Record<VoiceError, TKey> = { unavailable: 'voice.unavailable', denied: 'voice.denied', 'no-speech': 'voice.noSpeech', error: 'voice.error' };
/** Presses shorter than this are taps (toggle mode); longer ones are holds. */
const HOLD_MS = 350;

export function MicButton({ onFinal, onListeningChange, onTranscript, onUnavailable, size = 40, color }: Props) {
  const { c } = useTheme();
  const { t } = useT();
  const lang = useVoiceLang();
  const voice = useVoiceInput({
    lang,
    onFinal,
    onError: (e) => {
      toast(t(ERR[e]), e === 'unavailable' ? 'info' : 'warn');
      if (e === 'unavailable' || e === 'denied') onUnavailable?.();
    },
  });
  const pulse = useSharedValue(0);
  const pressedAt = useRef(0);
  const toggleStop = useRef(false);

  useEffect(() => {
    onListeningChange?.(voice.listening);
    if (voice.listening) pulse.set(withRepeat(withTiming(1, { duration: 900 }), -1, false));
    else {
      cancelAnimation(pulse);
      pulse.set(0);
    }
  }, [voice.listening, onListeningChange, pulse]);

  useEffect(() => {
    if (voice.transcript) onTranscript?.(voice.transcript);
  }, [voice.transcript, onTranscript]);

  const ring = useAnimatedStyle(() => ({ opacity: 0.55 * (1 - pulse.get()), transform: [{ scale: 1 + pulse.get() * 0.8 }] }));
  const accent = color ?? c.primary;

  return (
    <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      <Animated.View pointerEvents="none" style={[{ position: 'absolute', width: size, height: size, borderRadius: size / 2, backgroundColor: accent }, ring]} />
      <PressableScale
        hapticOnPress={false}
        scaleTo={0.9}
        delayLongPress={120}
        onPressIn={() => {
          // Second tap in tap-to-talk mode: stop and send.
          if (voice.isActive()) {
            toggleStop.current = true;
            haptic.light();
            voice.stop();
            return;
          }
          toggleStop.current = false;
          pressedAt.current = Date.now();
          haptic.medium();
          stopSpeaking();
          voice.start();
        }}
        onPressOut={() => {
          if (toggleStop.current) {
            toggleStop.current = false;
            return;
          }
          // Held long enough → release sends. A quick tap keeps listening.
          if (Date.now() - pressedAt.current >= HOLD_MS) voice.stop();
        }}
        accessibilityLabel={voice.listening ? t('voice.stopListening') : t('home.holdToTalk')}
        accessibilityHint={t('voice.hint')}
        accessibilityState={{ busy: voice.listening }}
        testID="mic-button"
        style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center', backgroundColor: voice.listening ? accent : c.surfaceStrong }}
      >
        <Icon name="mic" size={size * 0.48} color={voice.listening ? c.primaryText : c.text} fill={voice.listening ? c.primaryText : 'none'} />
      </PressableScale>
    </View>
  );
}
