/**
 * The character dock — Home's conversational entry point (SPEC §5.2).
 *
 * Docked above the tab bar: the chosen coach idles, a speech bubble cycles the
 * proactive nudges (rule-based insights from GET /nudges), and a pill composer
 * offers three ways in: tap to type, talk (hold or tap the mic; the FI / EN / SV
 * pill picks the spoken language), or snap a photo.
 * Everything routes to the full chat with the question prefilled or sent, so
 * the user never has to know "what to ask" — the coach suggests it.
 */
import { useCallback, useEffect, useState } from 'react';
import { View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { Nudge } from '@/api/types';
import { Character, PERSONAS, type CharacterState } from '@/characters';
import { MicButton } from '@/components/chat/MicButton';
import { VoiceLangPill } from '@/components/chat/VoiceLangPill';
import { pickImage } from '@/components/chat/pickImage';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { openChat } from '@/lib/chatNav';
import { useSession } from '@/store/session';
import { useUi } from '@/store/ui';
import { layout, makeStyles, useTheme } from '@/theme';

export function CharacterDock({ nudges }: { nudges: Nudge[] }) {
  const s = useStyles();
  const { c } = useTheme();
  const { t, locale } = useT();
  const insets = useSafeAreaInsets();
  const persona = useSession((st) => st.persona);
  const meta = PERSONAS[persona];
  const setPending = useUi((st) => st.setPendingAttachment);
  const [idx, setIdx] = useState(0);
  const [listening, setListening] = useState(false);
  const [partial, setPartial] = useState('');
  const [state, setState] = useState<CharacterState>('happy');

  useEffect(() => {
    const greet = setTimeout(() => setState('idle'), 2200);
    return () => clearTimeout(greet);
  }, []);

  useEffect(() => {
    if (nudges.length < 2) return;
    const id = setInterval(() => setIdx((i) => (i + 1) % nudges.length), 6000);
    return () => clearInterval(id);
  }, [nudges.length]);

  const onListening = useCallback((l: boolean) => {
    setListening(l);
    if (!l) setPartial('');
  }, []);

  const nudge = nudges.length ? nudges[idx % nudges.length] : null;
  const charState: CharacterState = listening ? 'listening' : nudge?.kind === 'celebrate' && state === 'idle' ? 'happy' : state;
  const bottom = insets.bottom + layout.tabBarHeight + layout.tabBarGap + 8;

  return (
    <View testID="character-dock" pointerEvents="box-none" style={[s.wrap, { paddingBottom: bottom }]}>
      <LinearGradient pointerEvents="none" colors={['transparent', `${c.bg[1]}EE`, c.bg[1]]} locations={[0, 0.22, 0.6]} style={s.fade} />
      <View style={s.column} pointerEvents="box-none">
        <View style={s.row} pointerEvents="box-none">
          <PressableScale onPress={() => openChat()} accessibilityLabel={meta.name} scaleTo={0.94}>
            <Character testID={`character-${persona}`} persona={persona} state={charState} size={96} locale={locale} />
          </PressableScale>
          {listening || nudge ? (
            <Animated.View key={listening ? 'listen' : nudge?.id} entering={FadeIn.duration(260)} exiting={FadeOut.duration(160)} style={s.bubbleWrap}>
              <PressableScale
                testID="nudge-bubble"
                onPress={() => nudge && openChat(nudge.action_prompt)}
                style={[s.bubble, { borderColor: `${meta.color}55` }]}
                accessibilityLabel={nudge?.text}
                accessibilityHint={nudge?.action_prompt}
              >
                <Text variant="caption" weight="600" numberOfLines={3}>
                  {listening ? partial || t('home.listening') : `${nudge?.emoji ?? ''} ${nudge?.text ?? ''}`}
                </Text>
                {!listening && nudge ? (
                  <Text variant="micro" color={meta.color} numberOfLines={1} style={{ marginTop: 4 }}>
                    {nudge.action_prompt} →
                  </Text>
                ) : null}
              </PressableScale>
              <View style={[s.tail, { borderRightColor: s.bubble.backgroundColor as string }]} />
            </Animated.View>
          ) : null}
        </View>
        <View style={s.composer}>
          <PressableScale
            testID="dock-composer"
            scaleTo={0.98}
            onPress={() => openChat()}
            style={s.field}
            accessibilityLabel={`${t('home.ask', { name: meta.name })} ${t('home.talkOrType')}`}
          >
            <Icon name="sparkle" size={18} color={meta.color} />
            <View style={{ flex: 1 }}>
              <Text variant="callout" weight="700" numberOfLines={1}>
                {t('home.ask', { name: meta.name })}
              </Text>
              <Text variant="micro" tone="muted" numberOfLines={1}>
                {t('home.talkOrType')}
              </Text>
            </View>
          </PressableScale>
          <PressableScale
            onPress={async () => {
              const img = await pickImage();
              if (img) {
                setPending(img);
                openChat(t('chat.imageQuestion'));
              }
            }}
            testID="camera-button"
            style={s.iconBtn}
            accessibilityLabel={t('chat.attach')}
          >
            <Icon name="camera" size={20} color={c.text} />
          </PressableScale>
          <VoiceLangPill height={36} />
          <MicButton
            size={44}
            color={meta.color}
            onListeningChange={onListening}
            onTranscript={setPartial}
            onFinal={(text, lang) => openChat(text, { voice: true, lang })}
            onUnavailable={() => openChat(undefined, { send: false })}
          />
        </View>
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { position: 'absolute', left: 0, right: 0, bottom: 0 },
  fade: { position: 'absolute', left: 0, right: 0, bottom: 0, top: -40 },
  column: { width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', paddingHorizontal: layout.gutter, gap: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  bubbleWrap: { flex: 1, justifyContent: 'center' },
  bubble: {
    backgroundColor: t.name === 'dark' ? 'rgba(20,44,33,0.96)' : '#FFFFFF',
    borderRadius: 18,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginLeft: 8,
    shadowColor: '#000',
    shadowOpacity: 0.25,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 6 },
    elevation: 6,
  },
  tail: {
    position: 'absolute',
    left: 0,
    top: '50%',
    marginTop: -7,
    width: 0,
    height: 0,
    borderTopWidth: 7,
    borderBottomWidth: 7,
    borderRightWidth: 9,
    borderTopColor: 'transparent',
    borderBottomColor: 'transparent',
  },
  composer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    padding: 6,
    paddingLeft: 6,
    borderRadius: t.radius.pill,
    backgroundColor: t.name === 'dark' ? 'rgba(16,36,27,0.96)' : 'rgba(255,255,255,0.97)',
    borderWidth: 1,
    borderColor: t.c.border,
    shadowColor: '#000',
    shadowOpacity: 0.3,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
    elevation: 10,
  },
  field: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, height: 44 },
  iconBtn: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surfaceStrong },
}));
