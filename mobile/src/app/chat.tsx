/**
 * CHAT — full-screen conversation with the coach (SPEC §5.3).
 *
 * The character sits large at the top and *performs the stream*: it thinks
 * while tools run (status events), talks while tokens arrive or TTS speaks,
 * then shows the answer's mood (happy / concerned / celebrate) for a few
 * seconds. Below it: messages with inline widgets, suggestion chips, sources
 * and feedback; the composer supports typing, hold-to-talk and photos.
 *
 * Deep-link params: `q` (question), `send=1` (send immediately), `voice=1`
 * (asked by voice: read the answer aloud) and `lang` (spoken language). A photo
 * picked on Home arrives through the UI store (`pendingAttachment`).
 *
 * Read-aloud: answers to spoken questions are read aloud automatically (if
 * Settings → Spoken answers is on); typed questions are not. A stop pill shows
 * while reading, and pressing the mic stops playback.
 */
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useEffectEvent, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, View, type ScrollViewInstance, type TextInputInstance } from 'react-native';
import Animated, { FadeIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useFeedback } from '@/api/hooks';
import type { Locale } from '@/api/types';
import { Character, PERSONAS, moodToState, type CharacterState } from '@/characters';
import { ChatBubble } from '@/components/chat/ChatBubble';
import { Composer } from '@/components/chat/Composer';
import { pickImage } from '@/components/chat/pickImage';
import { WidgetContext, type WidgetHost } from '@/components/widgets/context';
import { Background } from '@/components/ui/Background';
import { Chip } from '@/components/ui/Chip';
import { DemoBadge } from '@/components/ui/DemoBadge';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { useSpeech } from '@/hooks/useSpeech';
import { useT, type TKey } from '@/i18n';
import { haptic } from '@/lib/haptics';
import { useChat, type ChatStoreState } from '@/store/chat';
import { useSession } from '@/store/session';
import { toast, useUi, type PendingAttachment } from '@/store/ui';
import { layout, makeStyles, useTheme } from '@/theme';

const STARTERS: TKey[] = ['chat.starter1', 'chat.starter2', 'chat.starter3', 'chat.starter4', 'chat.starter5', 'chat.starter6'];

export default function ChatScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { t, locale } = useT();
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ q?: string; send?: string; voice?: string; lang?: string }>();
  const persona = useSession((st) => st.persona);
  const customerId = useSession((st) => st.customerId);
  const voiceOn = useSession((st) => st.voice);
  const setVoice = useSession((st) => st.setVoice);
  const meta = PERSONAS[persona];

  const messages = useChat((st) => st.messages);
  const streaming = useChat((st) => st.streaming);
  const feedback = useFeedback();
  const speech = useSpeech();

  // Initial composer content comes from the deep link (prefill-only) or a photo handed over from Home.
  const [input, setInput] = useState(() => (params.send !== '1' && typeof params.q === 'string' ? params.q : ''));
  const [attachment, setAttachment] = useState<PendingAttachment | null>(() => (params.send === '1' ? null : useUi.getState().pendingAttachment));
  const [listening, setListening] = useState(false);
  const [rest, setRest] = useState<CharacterState>('idle');
  const scrollRef = useRef<ScrollViewInstance>(null);
  const inputRef = useRef<TextInputInstance>(null);
  const handledParams = useRef(false);
  const restTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Language of the pending spoken question; null when the last question was typed. */
  const voiceTurn = useRef<Locale | null>(null);

  /** Show a mood for a few seconds, then relax back to idle. */
  const showMood = (mood: CharacterState, ms: number) => {
    setRest(mood);
    if (restTimer.current) clearTimeout(restTimer.current);
    restTimer.current = setTimeout(() => setRest('idle'), ms);
  };

  // Keep the conversation scoped to the active demo customer.
  useEffect(() => {
    if (customerId) useChat.getState().ensureCustomer(customerId);
  }, [customerId]);

  /** `spokenLang` is set when the question came from the mic. */
  const doSend = (text: string, img: PendingAttachment | null = null, spokenLang: Locale | null = null) => {
    const q = text.trim() || (img ? t('chat.imageQuestion') : '');
    if (!q) return;
    haptic.light();
    speech.stop();
    setInput('');
    setAttachment(null);
    voiceTurn.current = spokenLang;
    useChat.getState().send(q, img, spokenLang ? { locale: spokenLang } : undefined);
  };

  // Handle the deep-link / Home hand-off exactly once (guarded against StrictMode double effects).
  useEffect(() => {
    if (handledParams.current) return;
    handledParams.current = true;
    const ui = useUi.getState();
    const pending = ui.pendingAttachment;
    if (pending) ui.setPendingAttachment(null);
    const q = typeof params.q === 'string' ? params.q : '';
    const spoken = params.voice === '1' ? (['fi', 'en', 'sv'].includes(params.lang ?? '') ? (params.lang as Locale) : useSession.getState().locale) : null;
    voiceTurn.current = q && params.send === '1' ? spoken : null;
    if (q && params.send === '1') useChat.getState().send(q, pending, spoken ? { locale: spoken } : undefined);
    else setTimeout(() => inputRef.current?.focus(), 350);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /**
   * React to chat-store transitions (an answer finished, a widget asked to
   * celebrate): mood animation + optional read-aloud. Subscribing to the store
   * keeps these side effects out of render and fires exactly once per event.
   */
  const onStoreChange = useEffectEvent((st: ChatStoreState, prev: ChatStoreState) => {
    if (st.celebrateAt && st.celebrateAt !== prev.celebrateAt) showMood('celebrate', 3500);
    const last = st.messages[st.messages.length - 1];
    if (!last || last.role !== 'assistant' || !last.done) return;
    if (prev.messages.find((m) => m.id === last.id)?.done) return;
    const mood = moodToState(last.done.mood);
    showMood(mood, 4500);
    if (mood === 'celebrate') haptic.success();
    // Hands-free loop: only answers to spoken questions are read aloud.
    const spoken = voiceTurn.current;
    voiceTurn.current = null;
    const ses = useSession.getState();
    if (spoken && ses.voice && last.text) speech.speak(last.text, ses.persona, spoken);
  });
  useEffect(() => {
    const unsub = useChat.subscribe((st, prev) => onStoreChange(st, prev));
    return () => {
      unsub();
      if (restTimer.current) clearTimeout(restTimer.current);
    };
  }, []);

  const last = messages[messages.length - 1];
  const charState: CharacterState = listening
    ? 'listening'
    : streaming && last?.role === 'assistant' && !last.text
      ? 'thinking'
      : streaming || speech.speaking
        ? 'talking'
        : rest;

  const host: WidgetHost = { onPrompt: (text) => doSend(text), onCelebrate: () => useChat.getState().celebrate() };

  const close = () => {
    speech.stop();
    if (router.canGoBack()) router.back();
    else router.replace('/');
  };

  const onAttach = async () => {
    const img = await pickImage();
    if (img) setAttachment(img);
  };

  const onFeedback = (id: string, messageId: string | undefined, rating: 1 | -1) => {
    useChat.getState().setFeedback(id, rating);
    haptic.tap();
    if (messageId) feedback.mutate({ messageId, rating });
    toast(t('chat.thanks'), 'good');
  };

  const retryLast = () => {
    const lastUser = [...messages].reverse().find((m) => m.role === 'user');
    if (lastUser) doSend(lastUser.text);
  };

  const compact = messages.length > 0;
  const statusText = streaming ? (last?.status?.label || t('chat.thinking')) : meta.title[locale];

  return (
    <View style={s.root} testID="chat-screen">
      <Background />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'web' ? undefined : 'padding'} keyboardVerticalOffset={0}>
        <View style={[s.column, { paddingTop: Platform.OS === 'ios' ? 12 : insets.top + 8 }]}>
          {/* Header */}
          <View style={s.header}>
            <PressableScale testID="chat-close" onPress={close} style={s.headerBtn} accessibilityLabel={t('common.close')}>
              <Icon name={Platform.OS === 'ios' ? 'chevronDown' : 'chevronLeft'} size={22} color={c.text} />
            </PressableScale>
            <View style={s.headerMid}>
              <Text variant="callout" weight="800">
                {meta.name} {meta.emoji}
              </Text>
              <Text testID="chat-status" variant="micro" tone="muted" numberOfLines={1}>
                {statusText}
              </Text>
            </View>
            <PressableScale
              onPress={() => {
                const next = !voiceOn;
                setVoice(next);
                if (!next) speech.stop();
                toast(next ? t('chat.voiceOn') : t('chat.voiceOff'));
              }}
              style={[s.headerBtn, voiceOn && { backgroundColor: `${meta.color}2A` }]}
              accessibilityLabel={voiceOn ? t('chat.voiceOff') : t('chat.voiceOn')}
              accessibilityState={{ selected: voiceOn }}
            >
              <Icon name={voiceOn ? 'speaker' : 'speakerOff'} size={19} color={voiceOn ? meta.color : c.textMuted} />
            </PressableScale>
            <PressableScale
              onPress={() => {
                speech.stop();
                useChat.getState().reset();
                setRest('idle');
              }}
              style={s.headerBtn}
              accessibilityLabel={t('chat.newChat')}
            >
              <Icon name="refresh" size={18} color={c.textMuted} />
            </PressableScale>
          </View>

          {/* Character hero */}
          <View style={[s.hero, { height: compact ? 128 : 210 }]}>
            <View style={[s.halo, { backgroundColor: `${meta.color}1A`, width: compact ? 120 : 190, height: compact ? 120 : 190, borderRadius: 100 }]} />
            <Character testID={`character-${persona}`} persona={persona} state={charState} size={compact ? 118 : 190} locale={locale} haptics />
            <View style={s.badgeSpot}>
              <DemoBadge />
            </View>
          </View>

          {/* Messages */}
          <WidgetContext.Provider value={host}>
            <ScrollView
              ref={scrollRef}
              style={{ flex: 1 }}
              contentContainerStyle={s.messages}
              keyboardShouldPersistTaps="handled"
              keyboardDismissMode="interactive"
              showsVerticalScrollIndicator={false}
              onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
            >
              {messages.length === 0 ? (
                <Animated.View entering={FadeIn.delay(150)} style={s.empty}>
                  <Text variant="title" align="center">
                    {t('chat.emptyTitle')}
                  </Text>
                  <Text variant="callout" tone="muted" align="center">
                    {t('chat.emptySub')}
                  </Text>
                  <View style={s.starters}>
                    {STARTERS.map((k) => (
                      <Chip key={k} label={t(k)} icon="sparkle" color={meta.color} onPress={() => doSend(t(k))} />
                    ))}
                  </View>
                </Animated.View>
              ) : (
                messages.map((m, i) => (
                  <ChatBubble
                    key={m.id}
                    message={m}
                    isLast={i === messages.length - 1}
                    onSuggestion={(q) => doSend(q)}
                    onFeedback={(r) => onFeedback(m.id, m.done?.message_id, r)}
                    onSpeak={() => speech.speak(m.text, persona, locale)}
                    onRetry={retryLast}
                  />
                ))
              )}
            </ScrollView>
          </WidgetContext.Provider>

          {/* Composer */}
          <View style={{ paddingBottom: Math.max(insets.bottom, 12), paddingTop: 8 }}>
            {speech.speaking ? (
              <Animated.View entering={FadeIn.duration(180)} style={s.stopRow}>
                <PressableScale onPress={speech.stop} style={[s.stopPill, { borderColor: `${meta.color}66` }]} accessibilityLabel={t('voice.stopReading')} testID="stop-reading">
                  <Icon name="stop" size={14} color={meta.color} />
                  <Text variant="caption" weight="700">
                    {t('voice.stopReading')}
                  </Text>
                </PressableScale>
              </Animated.View>
            ) : null}
            <Composer
              ref={inputRef}
              value={input}
              onChange={setInput}
              onSend={() => doSend(input, attachment)}
              onStop={() => useChat.getState().stop()}
              onAttach={onAttach}
              onRemoveAttachment={() => setAttachment(null)}
              onVoice={(text, lang) => doSend(text, attachment, lang)}
              onListeningChange={setListening}
              attachment={attachment}
              streaming={streaming}
              placeholder={t('chat.placeholder', { name: meta.name })}
              color={meta.color}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  root: { flex: 1, backgroundColor: t.c.bgSolid, overflow: 'hidden' },
  column: { flex: 1, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center', paddingHorizontal: layout.gutter },
  header: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerBtn: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surface, borderWidth: 1, borderColor: t.c.border },
  headerMid: { flex: 1, alignItems: 'center' },
  hero: { alignItems: 'center', justifyContent: 'center' },
  halo: { position: 'absolute' },
  badgeSpot: { position: 'absolute', right: 0, top: 6 },
  messages: { gap: 16, paddingTop: 4, paddingBottom: 12 },
  empty: { gap: 10, paddingTop: 4 },
  stopRow: { alignItems: 'center', paddingBottom: 8 },
  stopPill: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, height: 44, borderRadius: 22, borderWidth: 1, backgroundColor: t.c.surfaceStrong },
  starters: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center', marginTop: 8 },
}));
