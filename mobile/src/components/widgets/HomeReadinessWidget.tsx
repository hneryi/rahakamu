/**
 * `home_readiness` widget — mortgage readiness from the dataset's real
 * approval ratios: down-payment progress, stress-tested income need and the
 * concrete gaps. Ends with a hand-off to S-Bank advisors (integration hook).
 */
import { View } from 'react-native';

import type { HomeReadiness } from '@/api/types';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { useTheme } from '@/theme';
import { Pill, WidgetCard } from './WidgetCard';

export function HomeReadinessWidget({ data }: { data: HomeReadiness }) {
  const { c } = useTheme();
  const { t, money } = useT();
  const color = data.verdict === 'ready' ? c.good : data.verdict === 'almost' ? c.amber : c.warn;
  const app = data.customer_application;
  return (
    <WidgetCard title={t('w.home.title')} emoji="🏡" tint={color} right={<Pill label={t(`w.home.verdict.${data.verdict}` as TKey)} color={color} />}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text variant="callout" tone="muted">
          {t('w.home.price')}
        </Text>
        <Text variant="body" weight="800" money>
          {money(data.property_price)}
        </Text>
      </View>
      <Row label={t('w.home.equity')} have={data.your_equity_estimate} need={data.equity_needed} />
      <Row label={t('w.home.income')} have={data.your_monthly_income} need={data.required_monthly_income} />
      {data.gaps?.map((g, i) => (
        <View key={i} style={{ flexDirection: 'row', gap: 8 }}>
          <Text variant="caption" color={c.warn}>
            •
          </Text>
          <Text variant="caption" style={{ flex: 1 }}>
            {g}
          </Text>
        </View>
      ))}
      {app ? (
        <View style={{ padding: 10, borderRadius: 14, backgroundColor: c.surface, gap: 2 }}>
          <Text variant="micro" tone="muted">
            {t('w.home.application').toUpperCase()}
          </Text>
          {Object.entries(app)
            .slice(0, 4)
            .map(([k, v]) => (
              <Text key={k} variant="caption">
                {k.replace(/_/g, ' ')}: {typeof v === 'number' ? money(v) : String(v)}
              </Text>
            ))}
        </View>
      ) : null}
      {data.dataset_note ? (
        <Text variant="caption" tone="faint">
          {data.dataset_note}
        </Text>
      ) : null}
    </WidgetCard>
  );
}

function Row({ label, have, need }: { label: string; have: number; need: number }) {
  const { c } = useTheme();
  const { t, money } = useT();
  const ok = have >= need;
  return (
    <View style={{ gap: 5 }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
        <Text variant="caption" weight="700">
          {label}
        </Text>
        <Text variant="caption" money>
          <Text variant="caption" weight="800" money color={ok ? c.good : c.text}>
            {money(have)}
          </Text>
          <Text variant="caption" tone="faint">
            {'  '}
            {t('w.home.need', { amount: money(need) })}
          </Text>
        </Text>
      </View>
      <ProgressBar value={need > 0 ? have / need : 1} color={ok ? c.good : c.amber} />
    </View>
  );
}
