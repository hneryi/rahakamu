/**
 * `goal_plan` widget: feasibility verdict, needed-vs-surplus, and concrete
 * leak-basket cuts that close the gap. "Create this goal" turns advice into a
 * commitment in one tap (POST /goals → caches invalidated → haptic + the
 * character celebrates) — the moment that converts a chat into behaviour change.
 */
import { useState } from 'react';
import { View } from 'react-native';

import { useCreateGoal } from '@/api/hooks';
import type { GoalCreate, GoalKind, GoalPlan } from '@/api/types';
import { Button } from '@/components/ui/Button';
import { Divider } from '@/components/ui/GlassCard';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { categoryLabel } from '@/i18n/categories';
import { haptic } from '@/lib/haptics';
import { toast } from '@/store/ui';
import { useTheme } from '@/theme';
import { useWidgetHost } from './context';
import { Pill, Stat, WidgetCard } from './WidgetCard';

export function guessKind(name: string): GoalKind {
  const n = name.toLowerCase();
  if (/car|auto/.test(n)) return 'car';
  if (/trip|travel|matka|loma|holiday|interrail/.test(n)) return 'travel';
  if (/home|house|asunto|koti|down/.test(n)) return 'home';
  if (/emergency|buffer|puskuri/.test(n)) return 'emergency';
  if (/study|school|course|opinn|education/.test(n)) return 'education';
  if (/laptop|phone|bike|gadget|kone|puhelin/.test(n)) return 'gadget';
  return 'other';
}

export function GoalPlanWidget({ data, createPayload }: { data: GoalPlan; createPayload?: GoalCreate }) {
  const { c } = useTheme();
  const { t, money, date, locale } = useT();
  const host = useWidgetHost();
  const create = useCreateGoal();
  const [created, setCreated] = useState(false);
  const color = data.feasibility === 'on_track' ? c.good : data.feasibility === 'stretch' ? c.amber : c.warn;
  const coverage = data.needed_per_month > 0 ? Math.min(1, (data.current_monthly_surplus + data.cuts_total) / data.needed_per_month) : 1;
  const name = data.name ?? t('goals.new');

  const onCreate = () => {
    create.mutate(
      createPayload
        ? { ...createPayload, kind: createPayload.kind ?? guessKind(createPayload.name ?? name) }
        : { name, target_amount: data.target_amount, deadline: data.deadline, saved_amount: data.saved_amount, kind: guessKind(name) },
      {
        onSuccess: () => {
          setCreated(true);
          haptic.success();
          toast(t('w.goalplan.created'), 'good');
          host.onCelebrate();
        },
        onError: (e) => toast(e instanceof Error ? e.message : t('common.error'), 'warn'),
      },
    );
  };

  return (
    <WidgetCard title={`${t('w.goalplan.title')} · ${name}`} emoji="🎯" right={<Pill label={t(`w.goalplan.${data.feasibility}` as TKey)} color={color} />}>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' }}>
        <Text variant="title" weight="800" money>
          {money(data.target_amount)}
        </Text>
        <Text variant="caption" tone="muted">
          {data.deadline ? t('goals.by', { date: date(data.deadline, true) }) : ''} · {t('common.months', { n: data.months })}
        </Text>
      </View>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <Stat label={t('w.goalplan.needed')} value={money(data.needed_per_month)} />
        <Stat label={t('w.goalplan.surplus')} value={money(data.current_monthly_surplus)} />
        <Stat label={t('w.goalplan.gap')} value={money(data.gap)} color={data.gap > 0 ? c.warn : c.good} />
      </View>
      <ProgressBar value={coverage} color={color} />
      {data.cuts?.length ? (
        <>
          <Divider />
          <Text variant="micro" tone="muted">
            {t('w.goalplan.cuts').toUpperCase()}
          </Text>
          {data.cuts.map((cut) => (
            <View key={cut.label} style={{ gap: 2 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <View style={{ width: 8, height: 8, borderRadius: 4, backgroundColor: c.basket.leak }} />
                <Text variant="callout" weight="600" style={{ flex: 1 }} numberOfLines={1}>
                  {categoryLabel(locale, cut.label)} −{cut.cut_pct}%
                </Text>
                <Text variant="callout" weight="700" money color={c.good}>
                  +{money(cut.monthly_saving)}
                  {t('common.perMonth')}
                </Text>
              </View>
              {cut.why ? (
                <Text variant="caption" tone="muted" style={{ paddingLeft: 16 }}>
                  {cut.why}
                </Text>
              ) : null}
            </View>
          ))}
        </>
      ) : null}
      {data.summary ? (
        <Text variant="caption" tone="muted">
          {data.summary}
        </Text>
      ) : null}
      {data.suggested_deadline ? (
        <Text variant="caption" weight="700" tone="amber">
          {t('w.goalplan.suggested', { date: date(data.suggested_deadline, true) })}
        </Text>
      ) : null}
      <Button
        label={created ? t('w.goalplan.created') : t('w.goalplan.create')}
        icon={created ? 'check' : 'target'}
        onPress={onCreate}
        loading={create.isPending}
        disabled={created}
        testID="create-goal"
        full
      />
    </WidgetCard>
  );
}
