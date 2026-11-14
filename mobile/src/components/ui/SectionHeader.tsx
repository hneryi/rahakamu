/**
 * Section title row. The optional "Ask about this" action is the bridge from any
 * piece of data to a conversation — the core interaction pattern of the app.
 */
import { View } from 'react-native';

import { useT } from '@/i18n';
import { openChat } from '@/lib/chatNav';
import { makeStyles, useTheme } from '@/theme';
import { Icon } from './Icon';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

type Props = { title: string; subtitle?: string; askPrompt?: string; action?: { label: string; onPress: () => void } };

export function SectionHeader({ title, subtitle, askPrompt, action }: Props) {
  const s = useStyles();
  return (
    <View style={s.row}>
      <View style={s.titles}>
        <Text variant="body" weight="700" accessibilityRole="header">
          {title}
        </Text>
        {subtitle ? (
          <Text variant="caption" tone="muted">
            {subtitle}
          </Text>
        ) : null}
      </View>
      {askPrompt ? <AskButton prompt={askPrompt} /> : null}
      {action ? (
        <PressableScale onPress={action.onPress} style={s.link}>
          <Text variant="caption" weight="700" tone="primary">
            {action.label}
          </Text>
        </PressableScale>
      ) : null}
    </View>
  );
}

export function AskButton({ prompt, label }: { prompt: string; label?: string }) {
  const s = useStyles();
  const { t } = useT();
  const { c } = useTheme();
  return (
    <PressableScale onPress={() => openChat(prompt)} style={s.ask} accessibilityLabel={label ?? t('common.askAbout')}>
      <Icon name="sparkle" size={13} color={c.accent} />
      <Text variant="micro" weight="700" tone="accent" numberOfLines={1}>
        {label ?? t('common.askAbout')}
      </Text>
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 10, marginTop: 6 },
  titles: { flex: 1, gap: 2 },
  link: { paddingVertical: 6, paddingHorizontal: 4 },
  ask: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: t.radius.pill,
    backgroundColor: `${t.c.accent}1A`,
    borderWidth: 1,
    borderColor: `${t.c.accent}40`,
  },
}));
