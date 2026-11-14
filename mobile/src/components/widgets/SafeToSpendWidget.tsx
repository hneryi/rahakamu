/**
 * `safe_to_spend` widget. Shows the per-day number big, then the transparent
 * waterfall (balance − bills − buffer − goals = safe) so the user learns the
 * formula, not just the answer.
 */
import { View } from 'react-native';

import type { SafeToSpend } from '@/api/types';
import { Divider } from '@/components/ui/GlassCard';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { useTheme } from '@/theme';
import { Pill, Stat, WidgetCard } from './WidgetCard';

export function statusColor(c: ReturnType<typeof useTheme>['c'], status: SafeToSpend['status']) {
  return status === 'comfortable' ? c.good : status === 'tight' ? c.amber : c.warn;
}

export function SafeToSpendWidget({ data }: { data: SafeToSpend }) {
  const { c } = useTheme();
  const { t, money, date } = useT();
  const color = statusColor(c, data.status);
  const rows: [string, number][] = [
    [t('home.balance'), data.balance],
    [t('w.safe.bills'), -sum(data.upcoming_bills?.map((b) => b.amount))],
    [t('w.safe.buffer'), -data.irregular_buffer],
    [t('w.safe.goals'), -data.goal_contributions],
  ];
  return (
    <WidgetCard title={t('w.safe.title')} emoji="🛡️" tint={color} right={<Pill label={t(`home.status.${data.status}` as TKey)} color={color} />}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 8 }}>
        <Text variant="hero" weight="800" money color={color}>
          {money(data.safe_per_day)}
        </Text>
        <Text variant="callout" tone="muted" style={{ marginBottom: 6 }}>
          {t('w.safe.perDay')}
        </Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Stat label={t('w.safe.week')} value={money(data.safe_this_week)} />
        <Stat label={t('w.safe.total')} value={money(data.safe_total)} />
        <Stat label={t('w.safe.payday')} value={date(data.next_payday)} />
      </View>
      <Divider />
      {rows.map(([label, v]) => (
        <View key={label} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <Text variant="caption" tone="muted">
            {label}
          </Text>
          <Text variant="caption" weight="600" money>
            {money(v)}
          </Text>
        </View>
      ))}
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text variant="caption" weight="800">
          = {t('w.safe.total')}
        </Text>
        <Text variant="caption" weight="800" money color={color}>
          {money(data.safe_total)}
        </Text>
      </View>
      {data.upcoming_bills?.length ? (
        <View style={{ gap: 4, marginTop: 4 }}>
          {data.upcoming_bills.slice(0, 4).map((b, i) => (
            <Text key={`${b.label}-${i}`} variant="caption" tone="faint">
              {date(b.expected_date)} · {b.label} · {money(b.amount)}
            </Text>
          ))}
        </View>
      ) : null}
    </WidgetCard>
  );
}

const sum = (xs?: number[]) => (xs ?? []).reduce((a, b) => a + b, 0);
