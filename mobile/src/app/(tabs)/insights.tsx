/**
 * INSIGHTS — the MyData explorer.
 *
 * Lets users browse their own data the way the agent sees it: basket trend by
 * month, spending by category with drill-down to the actual transactions,
 * their spender archetype, peer & Statistics Finland benchmarks, and recurring
 * payments. Every section ends in "Ask about this", turning curiosity into a
 * coached conversation with the context already filled in.
 */
import { useMemo, useState } from 'react';
import { View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { useBaskets, useBenchmarks, useOverview, useProfile, useRecurring, useSpending, useTransactions } from '@/api/hooks';
import type { BasketKey } from '@/api/types';
import { BarChart } from '@/components/charts/BarChart';
import { DonutChart } from '@/components/charts/DonutChart';
import { StackedBasketBars } from '@/components/charts/StackedBasketBars';
import { TxRow } from '@/components/home/TxRow';
import { DemoBadge } from '@/components/ui/DemoBadge';
import { GlassCard } from '@/components/ui/GlassCard';
import { Screen } from '@/components/ui/Screen';
import { AskButton, SectionHeader } from '@/components/ui/SectionHeader';
import { Segmented } from '@/components/ui/Segmented';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { BenchmarkView } from '@/components/widgets/BenchmarkWidget';
import { SpenderProfileView } from '@/components/widgets/SpenderProfileWidget';
import { AS_OF } from '@/api/fixtures';
import { categoryLabel, cadenceLabel } from '@/i18n/categories';
import { useT, type TKey } from '@/i18n';
import { useTheme } from '@/theme';

type Period = 1 | 3 | 6 | 12;
const BASKETS: BasketKey[] = ['fixed', 'irregular', 'leak'];
const PALETTE = ['#00B26F', '#5B8DEF', '#F5A524', '#FF6B8A', '#3DD9B4', '#A78BFA', '#94A3B8'];

function minusMonths(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() - n);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

export default function InsightsScreen() {
  const { c } = useTheme();
  const { t, money, month, monthLong, locale } = useT();
  const [period, setPeriod] = useState<Period>(3);
  const [selMonth, setSelMonth] = useState<number | undefined>(undefined);
  const [drill, setDrill] = useState<{ key: string; label: string } | null>(null);

  const asOf = useOverview().data?.as_of ?? AS_OF;
  const start = minusMonths(asOf, period);
  const baskets = useBaskets(Math.max(3, period));
  const spending = useSpending({ start, end: asOf, group_by: 'category' });
  const profile = useProfile();
  const bench = useBenchmarks();
  const recurring = useRecurring();

  const months = baskets.data?.months ?? [];
  const sel = selMonth !== undefined && selMonth < months.length ? months[selMonth] : months[months.length - 1];
  // Demo fixtures label groups with the raw category key; real payloads are already localized (unknown labels pass through).
  const groups = useMemo(() => (spending.data?.groups ?? []).map((g) => ({ ...g, label: categoryLabel(locale, g.label) })), [spending.data, locale]);
  const slices = useMemo(() => {
    const top = groups.slice(0, 6).map((g, i) => ({ label: g.label, value: g.total, color: PALETTE[i] }));
    const rest = groups.slice(6).reduce((a, g) => a + g.total, 0);
    return rest > 0 ? [...top, { label: '…', value: rest, color: PALETTE[6] }] : top;
  }, [groups]);

  const enter = (i: number) => FadeInDown.delay(50 * i).springify().damping(18);

  return (
    <Screen testID="insights-screen" title={t('ins.title')} subtitle={t('ins.sub')} right={<DemoBadge />}>
      <Segmented<Period>
        options={([1, 3, 6, 12] as Period[]).map((p) => ({ value: p, label: t(`ins.period.${p}` as TKey) }))}
        value={period}
        onChange={(p) => {
          setPeriod(p);
          setSelMonth(undefined);
        }}
      />

      {/* Basket trend */}
      <Animated.View entering={enter(0)}>
        <SectionHeader title={t('ins.trend')} askPrompt={t('ins.ask.trend', { n: Math.max(3, period) })} />
        <GlassCard style={{ gap: 12 }}>
          {months.length ? (
            <>
              <StackedBasketBars months={months} selected={selMonth ?? months.length - 1} onSelect={setSelMonth} />
              {sel ? (
                <View style={{ gap: 6 }}>
                  <Text variant="callout" weight="700">
                    {monthLong(sel.month)}
                  </Text>
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
                    {BASKETS.map((b) => (
                      <View key={b} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: '45%' }}>
                        <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: c.basket[b] }} />
                        <Text variant="caption" tone="muted">
                          {t(`basket.${b}.short` as TKey)}
                        </Text>
                        <Text variant="caption" weight="700" money>
                          {money(sel[b])}
                        </Text>
                      </View>
                    ))}
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, minWidth: '45%' }}>
                      <Text variant="caption" tone="muted">
                        {t('basket.income')}
                      </Text>
                      <Text variant="caption" weight="700" money color={c.good}>
                        {money(sel.income)}
                      </Text>
                    </View>
                  </View>
                </View>
              ) : null}
            </>
          ) : (
            <Skeleton height={190} />
          )}
        </GlassCard>
      </Animated.View>

      {/* Categories */}
      <Animated.View entering={enter(1)}>
        <SectionHeader title={t('ins.categories')} subtitle={t('ins.categoriesHint')} askPrompt={t('ins.ask.categories')} />
        <GlassCard style={{ gap: 16 }}>
          {spending.data ? (
            groups.length ? (
              <>
                <DonutChart slices={slices} size={140} legend={false} centerLabel={t('ins.txCount', { n: spending.data.count })} />
                <BarChart bars={groups.slice(0, 10).map((g, i) => ({ label: g.label, value: g.total, color: PALETTE[Math.min(i, 6)] }))} onPressBar={(_, i) => setDrill(groups[i] ? { key: groups[i].key, label: groups[i].label } : null)} />
              </>
            ) : (
              <EmptyState text={t('common.none')} />
            )
          ) : (
            <Skeleton height={220} />
          )}
        </GlassCard>
      </Animated.View>

      {/* Profile */}
      <Animated.View entering={enter(2)}>
        <SectionHeader title={t('ins.profile')} askPrompt={t('ins.ask.profile')} />
        <GlassCard>{profile.data ? <SpenderProfileView data={profile.data} /> : <Skeleton height={200} />}</GlassCard>
      </Animated.View>

      {/* Benchmarks */}
      <Animated.View entering={enter(3)}>
        <SectionHeader title={t('ins.benchmarks')} askPrompt={t('ins.ask.bench')} />
        <GlassCard>{bench.data ? <BenchmarkView data={bench.data} /> : <Skeleton height={260} />}</GlassCard>
      </Animated.View>

      {/* Recurring */}
      <Animated.View entering={enter(4)}>
        <SectionHeader title={t('ins.recurring')} askPrompt={t('ins.ask.recurring')} />
        <GlassCard style={{ gap: 4 }}>
          {recurring.data ? (
            <>
              <Text variant="caption" tone="muted" money>
                {t('ins.recurringTotal', { amount: money(recurring.data.monthly_total) })}
              </Text>
              {recurring.data.items.map((r, i) => (
                <View key={`${r.label}-${i}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8 }}>
                  <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c.basket[r.basket] ?? c.textMuted }} />
                  <View style={{ flex: 1 }}>
                    <Text variant="callout" weight="600" numberOfLines={1}>
                      {r.label}
                    </Text>
                    <Text variant="caption" tone="muted">
                      {categoryLabel(locale, r.category)} · {cadenceLabel(locale, r.cadence)}
                      {r.day_of_month ? ` · ${t('ins.day', { n: r.day_of_month })}` : ''}
                    </Text>
                  </View>
                  <Text variant="callout" weight="700" money>
                    {money(r.avg_amount)}
                  </Text>
                </View>
              ))}
            </>
          ) : (
            <Skeleton height={160} />
          )}
        </GlassCard>
      </Animated.View>

      <CategorySheet category={drill} start={start} end={asOf} onClose={() => setDrill(null)} />
      <Text variant="micro" tone="faint" align="center">
        {month(start.slice(0, 7))} – {month(asOf.slice(0, 7))} · {asOf}
      </Text>
    </Screen>
  );
}

function CategorySheet({ category, start, end, onClose }: { category: { key: string; label: string } | null; start: string; end: string; onClose: () => void }) {
  const { t, money } = useT();
  const tx = useTransactions({ category: category?.key, start, end, limit: 40 }, !!category);
  const items = (tx.data?.items ?? []).filter((x) => x.amount < 0);
  const total = items.reduce((a, x) => a + Math.abs(x.amount), 0);
  return (
    <Sheet visible={!!category} onClose={onClose} title={category?.label ?? ''}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Text variant="callout" tone="muted">
          {t('ins.txCount', { n: tx.data?.total_count ?? 0 })}
        </Text>
        <AskButton prompt={t('ins.ask.category', { category: category?.label ?? '' })} />
      </View>
      {tx.isLoading ? (
        <Skeleton height={200} />
      ) : (
        <View>
          {items.map((x) => (
            <TxRow key={x.id} tx={x} compact />
          ))}
          {items.length ? (
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingTop: 10 }}>
              <Text variant="callout" weight="700">
                {t('w.tx.total')}
              </Text>
              <Text variant="callout" weight="800" money>
                {money(total)}
              </Text>
            </View>
          ) : (
            <EmptyState text={t('common.none')} />
          )}
        </View>
      )}
    </Sheet>
  );
}
