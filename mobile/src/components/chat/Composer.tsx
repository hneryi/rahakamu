/**
 * Chat composer: multi-line input, photo attach, mic (hold or tap) with a
 * FI / EN / SV speech-language pill, and a send button that becomes "stop"
 * while the coach is answering. The mic shows when the field is empty and the
 * send arrow when there is text (the messaging-app pattern users know); while
 * listening the interim words appear live in the field.
 */
import { Image } from 'expo-image';
import { forwardRef, useCallback, useState } from 'react';
import { Platform, TextInput, View, type TextInputInstance } from 'react-native';

import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { useT } from '@/i18n';
import type { Locale } from '@/api/types';
import type { PendingAttachment } from '@/store/ui';
import { fontFamily, makeStyles, useTheme } from '@/theme';
import { MicButton } from './MicButton';
import { VoiceLangPill } from './VoiceLangPill';

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop: () => void;
  onAttach: () => void;
  onRemoveAttachment: () => void;
  onVoice: (text: string, lang: Locale) => void;
  onListeningChange: (l: boolean) => void;
  attachment: PendingAttachment | null;
  streaming: boolean;
  placeholder: string;
  color: string;
};

export const Composer = forwardRef<TextInputInstance, Props>(function Composer(p, ref) {
  const s = useStyles();
  const { c } = useTheme();
  const { t } = useT();
  const [listening, setListening] = useState(false);
  const canSend = (!!p.value.trim() || !!p.attachment) && !listening;
  const onListening = useCallback(
    (l: boolean) => {
      setListening(l);
      p.onListeningChange(l);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [p.onListeningChange],
  );
  return (
    <View style={s.wrap}>
      {p.attachment ? (
        <View style={s.attachRow}>
          <Image source={{ uri: p.attachment.uri }} style={s.thumb} contentFit="cover" />
          <PressableScale onPress={p.onRemoveAttachment} style={s.removeThumb} accessibilityLabel={t('common.delete')}>
            <Icon name="close" size={12} color="#fff" />
          </PressableScale>
        </View>
      ) : null}
      <View style={s.bar}>
        <PressableScale testID="chat-attach" onPress={p.onAttach} style={s.round} accessibilityLabel={t('chat.attach')}>
          <Icon name="camera" size={20} color={c.text} />
        </PressableScale>
        <TextInput
          ref={ref}
          testID="chat-input"
          value={p.value}
          onChangeText={p.onChange}
          placeholder={p.placeholder}
          placeholderTextColor={c.textFaint}
          style={s.input}
          multiline
          maxLength={800}
          returnKeyType="send"
          submitBehavior="submit"
          onSubmitEditing={() => canSend && p.onSend()}
          onKeyPress={
            Platform.OS === 'web'
              ? (e) => {
                  // Web: Enter sends, Shift+Enter inserts a newline (messaging-app convention).
                  const ne = e.nativeEvent as unknown as { key: string; shiftKey?: boolean };
                  if (ne.key === 'Enter' && !ne.shiftKey) {
                    e.preventDefault();
                    if (canSend) p.onSend();
                  }
                }
              : undefined
          }
          accessibilityLabel={p.placeholder}
        />
        {p.streaming ? (
          <PressableScale testID="chat-stop" onPress={p.onStop} style={[s.round, { backgroundColor: c.surfaceStrong }]} accessibilityLabel={t('chat.stop')}>
            <Icon name="stop" size={18} color={c.text} />
          </PressableScale>
        ) : canSend ? (
          <PressableScale testID="chat-send" onPress={p.onSend} style={[s.round, { backgroundColor: p.color }]} accessibilityLabel={t('chat.send')}>
            <Icon name="send" size={20} color={c.primaryText} />
          </PressableScale>
        ) : (
          <View style={s.voice}>
            <VoiceLangPill height={36} />
            <MicButton size={44} color={p.color} onFinal={p.onVoice} onListeningChange={onListening} onTranscript={p.onChange} onUnavailable={() => (ref as React.RefObject<TextInputInstance | null>)?.current?.focus()} />
          </View>
        )}
      </View>
    </View>
  );
});

const useStyles = makeStyles((t) => ({
  wrap: { gap: 8 },
  attachRow: { flexDirection: 'row', paddingLeft: 52 },
  thumb: { width: 64, height: 64, borderRadius: 14, borderWidth: 1, borderColor: t.c.border },
  removeThumb: { position: 'absolute', left: 52 + 44, top: -10, width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(0,0,0,0.7)', alignItems: 'center', justifyContent: 'center' },
  bar: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    padding: 6,
    borderRadius: 26,
    backgroundColor: t.name === 'dark' ? 'rgba(16,36,27,0.96)' : '#FFFFFF',
    borderWidth: 1,
    borderColor: t.c.border,
  },
  voice: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  round: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surfaceStrong },
  input: { flex: 1, minHeight: 44, maxHeight: 120, color: t.c.text, fontSize: 16, lineHeight: 21, fontFamily, paddingTop: 12, paddingBottom: 11, paddingHorizontal: 4 },
}));
