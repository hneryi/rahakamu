/**
 * `survival_plan` widget — "how do I make it to payday with X €?".
 * Bills first, then a per-day number and simple category budgets compared with
 * what the user typically spends in the same period. Practical, not preachy.
 */
import { View } from 'react-native';

import type { SurvivalPlan } from '@/api/types';
import { Divider } from '@/components/ui/GlassCard';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { categoryLabel } from '@/i18n/categories';
import { useTheme } from '@/theme';
import { Pill, Stat, WidgetCard } from './WidgetCard';

export function SurvivalPlanWidget({ data }: { data: SurvivalPlan }) {
  const { c } = useTheme();
  const { t, money, date, locale } = useT();
  const color = data.risk === 'ok' ? c.good : data.risk === 'tight' ? c.amber : c.warn;
  return (
    <WidgetCard title={`${t('w.survival.title')} · ${t('common.days', { n: data.days })}`} emoji="🧭" tint={color} right={<Pill label={t(`w.survival.risk.${data.risk}` as TKey)} color={color} />}>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Stat label={t('w.survival.free')} value={money(data.free_money)} color={data.free_money < 0 ? c.warn : c.text} />
        <Stat label={t('w.survival.perDay')} value={money(data.per_day)} color={color} big />
        <Stat label={t('w.survival.perWeek')} value={money(data.per_week)} />
      </View>
      {data.shortfall > 0 ? (
        <Text variant="callout" weight="700" color={c.warn}>
          {t('w.survival.short', { amount: money(data.shortfall) })}
        </Text>
      ) : null}
      {data.bills?.length ? (
        <View style={{ gap: 3 }}>
          <Text variant="micro" tone="muted">
            {t('w.safe.bills').toUpperCase()} · {money(data.upcoming_bills_total)}
          </Text>
          {data.bills.slice(0, 5).map((b, i) => (
            <Text key={`${b.label}-${i}`} variant="caption" tone="faint">
              {b.expected_date ? `${date(b.expected_date)} · ` : ''}
              {b.label} · {money(b.amount)}
            </Text>
          ))}
        </View>
      ) : null}
      <Divider />
      <Text variant="micro" tone="muted">
        {t('w.survival.budgets').toUpperCase()}
      </Text>
      {data.category_budgets?.map((b) => (
        <View key={b.category} style={{ gap: 4 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
            <Text variant="caption" weight="700">
              {b.label ?? categoryLabel(locale, b.category)}
            </Text>
            <Text variant="caption" money>
              <Text variant="caption" weight="800" money>
                {money(b.budget)}
              </Text>
              <Text variant="caption" tone="faint">
                {'  '}
                {t('w.survival.typical', { amount: money(b.typical) })}
              </Text>
            </Text>
          </View>
          <ProgressBar value={b.typical > 0 ? Math.min(1, b.budget / b.typical) : 1} color={b.budget >= b.typical ? c.good : c.amber} />
        </View>
      ))}
      {data.tips?.length ? (
        <View style={{ gap: 6, marginTop: 4 }}>
          {data.tips.slice(0, 4).map((tip, i) => (
            <View key={i} style={{ flexDirection: 'row', gap: 8 }}>
              <Text variant="caption" color={c.accent}>
                ✓
              </Text>
              <Text variant="caption" tone="muted" style={{ flex: 1 }}>
                {tip}
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </WidgetCard>
  );
}
