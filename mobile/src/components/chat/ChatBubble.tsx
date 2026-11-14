/**
 * One chat turn. User turns are compact green bubbles (with an optional photo).
 * Assistant turns are "rich": live status line while tools run, inline
 * generative-UI widgets, streamed markdown-lite text with a caret, and — once
 * `done` arrives — a transparent sources chip ("Based on 42 transactions"),
 * 👍/👎 feedback and read-aloud. Transparency about *where numbers come from*
 * is how an AI coach earns trust with money.
 */
import { Image } from 'expo-image';
import { useState } from 'react';
import { ActivityIndicator, View } from 'react-native';
import Animated, { FadeIn, FadeInDown, FadeInUp } from 'react-native-reanimated';

import { PERSONAS } from '@/characters';
import { Chip } from '@/components/ui/Chip';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { WidgetRenderer } from '@/components/widgets/WidgetRenderer';
import { useT } from '@/i18n';
import type { ChatMessage } from '@/store/chat';
import { useSession } from '@/store/session';
import { makeStyles, useTheme } from '@/theme';
import { Markdown } from './Markdown';

type Props = {
  message: ChatMessage;
  isLast: boolean;
  onSuggestion: (text: string) => void;
  onFeedback: (rating: 1 | -1) => void;
  onSpeak: () => void;
  onRetry: () => void;
};

export function ChatBubble({ message: m, isLast, onSuggestion, onFeedback, onSpeak, onRetry }: Props) {
  const s = useStyles();
  const { c } = useTheme();
  const { t } = useT();
  const persona = useSession((st) => st.persona);
  const meta = PERSONAS[persona];
  const [sourcesOpen, setSourcesOpen] = useState(false);

  if (m.role === 'user') {
    return (
      <Animated.View testID="message-user" entering={FadeInUp.springify().damping(18)} style={s.userWrap}>
        {m.imageUri ? <Image source={{ uri: m.imageUri }} style={s.photo} contentFit="cover" /> : null}
        {m.text ? (
          <View style={s.user}>
            <Text variant="callout" color={c.primaryText} weight="500">
              {m.text}
            </Text>
          </View>
        ) : null}
      </Animated.View>
    );
  }

  const waiting = m.streaming && !m.text && m.widgets.length === 0;
  return (
    <Animated.View testID="message-assistant" entering={FadeInDown.springify().damping(18)} style={s.botWrap}>
      {m.offline ? (
        <Text variant="micro" color={c.amber}>
          ● {t('chat.offline')}
        </Text>
      ) : null}
      {m.status && m.streaming ? (
        <Animated.View entering={FadeIn} style={s.status}>
          <ActivityIndicator size="small" color={meta.color} />
          <Text variant="caption" tone="muted" numberOfLines={1} style={{ flex: 1 }}>
            {m.status.label || t('chat.thinking')}
          </Text>
        </Animated.View>
      ) : waiting ? (
        <View style={s.status}>
          <ActivityIndicator size="small" color={meta.color} />
          <Text variant="caption" tone="muted">
            {t('chat.thinking')}
          </Text>
        </View>
      ) : null}

      {m.widgets.map((w) => (
        <WidgetRenderer key={w.id} widget={w} siblings={m.widgets} />
      ))}

      {m.text ? (
        <View style={[s.bot, { borderColor: `${meta.color}33` }]}>
          <Markdown text={m.text + (m.streaming ? ' ▍' : '')} />
        </View>
      ) : null}

      {m.error ? (
        <View style={s.errorRow}>
          <Text testID="chat-error" variant="caption" tone="warn" style={{ flex: 1 }}>
            {m.errorDetail || t('chat.error')}
          </Text>
          <Chip label={t('common.retry')} icon="refresh" onPress={onRetry} small />
        </View>
      ) : null}

      {m.done ? (
        <View style={s.footer}>
          <PressableScale testID="sources-chip" onPress={() => setSourcesOpen((v) => !v)} style={s.sources} accessibilityState={{ expanded: sourcesOpen }}>
            <Icon name="shield" size={14} color={c.accent} />
            <Text variant="micro" weight="700" tone="muted" numberOfLines={1} style={{ flexShrink: 1 }}>
              {m.done.sources?.tx_count ? t('chat.based', { n: m.done.sources.tx_count, period: m.done.sources.period ?? '' }) : t('chat.general')}
            </Text>
            <Icon name={sourcesOpen ? 'chevronDown' : 'chevronRight'} size={12} color={c.textFaint} />
          </PressableScale>
          <View style={s.actions}>
            <IconAction testID="speak-answer" icon="speaker" onPress={onSpeak} label={t('chat.voiceOn')} />
            <IconAction testID="feedback-up" icon="thumbUp" active={m.feedback === 1} onPress={() => onFeedback(1)} label={t('chat.helpful')} />
            <IconAction testID="feedback-down" icon="thumbDown" active={m.feedback === -1} onPress={() => onFeedback(-1)} label={t('chat.notHelpful')} />
          </View>
        </View>
      ) : null}
      {m.done && sourcesOpen ? (
        <Animated.View entering={FadeIn} style={s.sourcesBox}>
          <Text variant="micro" tone="muted">
            {t('chat.toolsUsed').toUpperCase()}
          </Text>
          {(m.tools.length ? m.tools.map((x) => `${x.name} — ${x.summary}`) : (m.done.sources?.tools ?? [])).map((line, i) => (
            <Text key={i} variant="caption" tone="faint">
              • {line}
            </Text>
          ))}
        </Animated.View>
      ) : null}

      {isLast && m.done?.suggestions?.length ? (
        <View style={s.suggestions}>
          {m.done.suggestions.slice(0, 3).map((q) => (
            <Chip testID="suggestion-chip" key={q} label={q} icon="sparkle" color={meta.color} onPress={() => onSuggestion(q)} />
          ))}
        </View>
      ) : null}
    </Animated.View>
  );
}

function IconAction({ icon, onPress, active, label, testID }: { icon: 'speaker' | 'thumbUp' | 'thumbDown'; onPress: () => void; active?: boolean; label: string; testID?: string }) {
  const { c } = useTheme();
  return (
    <PressableScale testID={testID} onPress={onPress} accessibilityLabel={label} accessibilityState={{ selected: !!active }} style={{ width: 44, height: 44, alignItems: 'center', justifyContent: 'center' }}>
      <Icon name={icon} size={19} color={active ? c.primary : c.textMuted} fill={active ? `${c.primary}44` : 'none'} />
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  userWrap: { alignSelf: 'flex-end', maxWidth: '85%', gap: 6, alignItems: 'flex-end' },
  user: { backgroundColor: t.c.primary, borderRadius: 22, borderBottomRightRadius: 6, paddingHorizontal: 16, paddingVertical: 10 },
  photo: { width: 180, height: 180, borderRadius: 18, borderWidth: 1, borderColor: t.c.border },
  botWrap: { alignSelf: 'stretch', gap: 10 },
  bot: { backgroundColor: t.c.surface, borderWidth: 1, borderRadius: 22, borderTopLeftRadius: 6, paddingHorizontal: 16, paddingVertical: 12, alignSelf: 'flex-start', maxWidth: '100%' },
  status: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 4 },
  errorRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  footer: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  sources: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, minHeight: 44, borderRadius: t.radius.pill, backgroundColor: t.c.surface, borderWidth: 1, borderColor: t.c.border, flexShrink: 1 },
  sourcesBox: { padding: 12, borderRadius: 16, backgroundColor: t.c.surface, gap: 3 },
  actions: { flexDirection: 'row', alignItems: 'center', marginRight: -10 },
  suggestions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 2 },
}));
