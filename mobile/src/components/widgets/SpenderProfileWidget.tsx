/**
 * `spender_profile` widget (+ a frameless view reused on Insights).
 * The archetype gives users a memorable, non-judgemental identity
 * ("Weekend Treater") and the trait bars show *why* — data-backed self-insight.
 */
import { View } from 'react-native';

import type { SpenderProfile } from '@/api/types';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { useTheme } from '@/theme';
import { Stat, WidgetCard } from './WidgetCard';

export function SpenderProfileView({ data }: { data: SpenderProfile }) {
  const { c } = useTheme();
  const { t, pct } = useT();
  return (
    <View style={{ gap: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 14 }}>
        <View style={{ width: 64, height: 64, borderRadius: 22, backgroundColor: `${c.accent}1F`, alignItems: 'center', justifyContent: 'center' }}>
          <Text style={{ fontSize: 34, lineHeight: 42 }}>{data.archetype.emoji}</Text>
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text variant="title" weight="800">
            {data.archetype.name}
          </Text>
          <Text variant="caption" tone="muted">
            {data.archetype.description}
          </Text>
        </View>
      </View>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Stat label={t('w.profile.savingsRate')} value={pct(data.savings_rate)} color={data.savings_rate > 0.1 ? c.good : c.amber} />
        <Stat label={t('w.profile.leakShare')} value={pct(data.leak_share)} color={data.leak_share > 0.35 ? c.basket.leak : c.text} />
      </View>
      {data.traits?.map((tr) => (
        <View key={tr.key} style={{ gap: 4 }}>
          <Text variant="caption" weight="700">
            {tr.label}
          </Text>
          {tr.detail ? (
            <Text variant="caption" tone="muted" numberOfLines={2}>
              {tr.detail}
            </Text>
          ) : null}
          <ProgressBar value={tr.score / 100} color={tr.key === 'saver' ? c.good : tr.score > 66 ? c.basket.leak : c.accent} />
        </View>
      ))}
    </View>
  );
}

export function SpenderProfileWidget({ data }: { data: SpenderProfile }) {
  const { t } = useT();
  return (
    <WidgetCard title={t('w.profile.title')} emoji="🧬">
      <SpenderProfileView data={data} />
    </WidgetCard>
  );
}
