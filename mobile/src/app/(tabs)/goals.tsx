/**
 * GOALS — "save with a plan, not a wish".
 *
 * Each goal shows a progress ring, what is left and the monthly pace. Creating
 * a goal shows a *live plan preview* (POST /goals/plan, debounced while typing):
 * is it on track, a stretch or unrealistic — and which leak-basket cuts would
 * close the gap. Seeing the trade-off before committing is the lesson.
 */
import { useLocalSearchParams, router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { TextInput, View } from 'react-native';
import Animated, { FadeInDown, LinearTransition } from 'react-native-reanimated';

import { AS_OF } from '@/api/fixtures';
import { useCreateGoal, useDeleteGoal, useGoalPlan, useGoals, useOverview, useUpdateGoal } from '@/api/hooks';
import type { Goal, GoalKind } from '@/api/types';
import { ProgressRing } from '@/components/charts/ProgressRing';
import { Button } from '@/components/ui/Button';
import { Chip } from '@/components/ui/Chip';
import { DemoBadge } from '@/components/ui/DemoBadge';
import { GlassCard } from '@/components/ui/GlassCard';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Screen } from '@/components/ui/Screen';
import { AskButton } from '@/components/ui/SectionHeader';
import { Sheet } from '@/components/ui/Sheet';
import { Skeleton } from '@/components/ui/Skeleton';
import { EmptyState, ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { Pill } from '@/components/widgets/WidgetCard';
import { useDebounced } from '@/hooks/useDebounced';
import { useT, type TKey } from '@/i18n';
import { confirmAsync } from '@/lib/confirm';
import { haptic } from '@/lib/haptics';
import { toast } from '@/store/ui';
import { fontFamily, makeStyles, useTheme } from '@/theme';

const KINDS: { kind: GoalKind; emoji: string }[] = [
  { kind: 'emergency', emoji: '🛟' },
  { kind: 'travel', emoji: '✈️' },
  { kind: 'car', emoji: '🚗' },
  { kind: 'home', emoji: '🏡' },
  { kind: 'gadget', emoji: '💻' },
  { kind: 'education', emoji: '🎓' },
  { kind: 'other', emoji: '🎯' },
];
const MONTH_OPTIONS = [6, 12, 18, 24, 36];

function addMonthsIso(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCMonth(d.getUTCMonth() + n);
  return d.toISOString().slice(0, 10);
}

function monthsUntil(from: string, to: string | null): number | null {
  if (!to) return null;
  const a = new Date(`${from}T00:00:00Z`);
  const b = new Date(`${to.slice(0, 10)}T00:00:00Z`);
  return Math.max(1, Math.round((b.getTime() - a.getTime()) / (30.4 * 86_400_000)));
}

const parseAmount = (s: string) => {
  const n = Number(s.replace(/\s/g, '').replace(',', '.'));
  return Number.isFinite(n) && n >= 0 ? n : 0;
};

export default function GoalsScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { t, money, date, pct } = useT();
  const params = useLocalSearchParams<{ new?: string }>();
  const goals = useGoals();
  const [editing, setEditing] = useState<Goal | 'new' | null>(null);
  // A fresh key per opening remounts the sheet so its form initialises from the goal.
  const [sheetKey, setSheetKey] = useState(0);
  const openSheet = (g: Goal | 'new') => {
    setEditing(g);
    setSheetKey((k) => k + 1);
  };

  // Deep link from Home ("+ New goal" → /goals?new=1): derived state, handled during render.
  const [seenNewParam, setSeenNewParam] = useState(false);
  if (params.new === '1' && !seenNewParam) {
    setSeenNewParam(true);
    openSheet('new');
  } else if (params.new !== '1' && seenNewParam) {
    setSeenNewParam(false);
  }
  useEffect(() => {
    if (params.new === '1') router.setParams({ new: undefined });
  }, [params.new]);

  const list = goals.data ?? [];
  const totalSaved = list.reduce((a, g) => a + g.saved_amount, 0);
  const totalTarget = list.reduce((a, g) => a + g.target_amount, 0);

  return (
    <Screen
      testID="goals-screen"
      title={t('goals.title')}
      subtitle={t('goals.sub')}
      right={
        <View style={{ alignItems: 'flex-end', gap: 8 }}>
          <PressableScale onPress={() => openSheet('new')} style={s.addBtn} accessibilityLabel={t('goals.new')}>
            <Icon name="plus" size={22} color={c.primaryText} />
          </PressableScale>
          <DemoBadge />
        </View>
      }
      onRefresh={() => goals.refetch()}
      refreshing={goals.isRefetching}
    >
      {goals.isLoading ? (
        <View style={{ gap: 12 }}>
          <Skeleton height={110} radius={24} />
          <Skeleton height={140} radius={24} />
          <Skeleton height={140} radius={24} />
        </View>
      ) : goals.isError ? (
        <ErrorState onRetry={() => goals.refetch()} />
      ) : list.length === 0 ? (
        <GlassCard>
          <EmptyState emoji="🎯" text={t('goals.empty')} />
          <Button label={t('goals.new')} icon="plus" onPress={() => openSheet('new')} full />
        </GlassCard>
      ) : (
        <>
          <GlassCard style={s.summary} tint={c.primary}>
            <ProgressRing progress={totalTarget ? totalSaved / totalTarget : 0} size={76} stroke={8} color={c.primary}>
              <Text variant="caption" weight="800" money>
                {pct(totalTarget ? totalSaved / totalTarget : 0)}
              </Text>
            </ProgressRing>
            <View style={{ flex: 1, gap: 2 }}>
              <Text variant="title" weight="800" money>
                {money(totalSaved)}
              </Text>
              <Text variant="caption" tone="muted" money>
                / {money(totalTarget)}
              </Text>
            </View>
          </GlassCard>
          {list.map((g, i) => {
            const done = g.progress >= 1;
            const left = Math.max(0, g.target_amount - g.saved_amount);
            return (
              <Animated.View key={g.id} entering={FadeInDown.delay(i * 60).springify().damping(18)} layout={LinearTransition}>
                <GlassCard style={s.goal}>
                  <PressableScale scaleTo={0.98} onPress={() => openSheet(g)} style={s.goalTop} accessibilityLabel={`${t('goals.edit')}: ${g.name} ${pct(g.progress)}`}>
                    <ProgressRing progress={g.progress} size={70} stroke={7} color={done ? c.good : c.primary}>
                      <Text variant="title">{g.emoji}</Text>
                    </ProgressRing>
                    <View style={{ flex: 1, gap: 3 }}>
                      <Text variant="body" weight="700" numberOfLines={1}>
                        {g.name}
                      </Text>
                      <Text variant="callout" weight="700" money>
                        {money(g.saved_amount)}{' '}
                        <Text variant="caption" tone="muted" money>
                          / {money(g.target_amount)}
                        </Text>
                      </Text>
                      <Text variant="caption" tone="muted" numberOfLines={1}>
                        {done ? t('home.goalDone') : `${t('home.goalLeft', { amount: money(left) })} · ${t('goals.monthly', { amount: money(g.monthly_contribution) })}`}
                      </Text>
                    </View>
                    <Icon name="edit" size={18} color={c.textFaint} />
                  </PressableScale>
                  <ProgressBar value={g.progress} color={done ? c.good : c.primary} />
                  <View style={s.goalBottom}>
                    <Text variant="micro" tone="faint">
                      {g.deadline ? t('goals.by', { date: date(g.deadline, true) }) : t('goals.noDeadline')}
                    </Text>
                    <AskButton prompt={t('goals.ask', { name: g.name })} />
                  </View>
                </GlassCard>
              </Animated.View>
            );
          })}
        </>
      )}
      <GoalSheet key={sheetKey} goal={editing} onClose={() => setEditing(null)} />
    </Screen>
  );
}

/** Create / edit sheet with live plan preview. */
function GoalSheet({ goal, onClose }: { goal: Goal | 'new' | null; onClose: () => void }) {
  const s = useStyles();
  const { c } = useTheme();
  const { t, money, date } = useT();
  const asOf = useOverview().data?.as_of ?? AS_OF;
  const isNew = goal === 'new';
  const existing = goal && goal !== 'new' ? goal : null;
  const create = useCreateGoal();
  const update = useUpdateGoal();
  const remove = useDeleteGoal();

  // Form state initialises from the goal at mount (the parent re-keys the sheet per opening).
  const [name, setName] = useState(existing?.name ?? '');
  const [kind, setKind] = useState<GoalKind>(existing?.kind ?? 'other');
  const [target, setTarget] = useState(existing ? String(Math.round(existing.target_amount)) : '');
  const [saved, setSaved] = useState(existing ? String(Math.round(existing.saved_amount)) : '');
  const [months, setMonths] = useState<number | null>(existing ? monthsUntil(asOf, existing.deadline) : 12);

  const targetN = parseAmount(target);
  const savedN = parseAmount(saved);
  const deadline = months ? addMonthsIso(asOf, months) : null;
  const planReq = useMemo(() => (targetN > 0 ? { target_amount: targetN, saved_amount: savedN, deadline, name: name || null } : null), [targetN, savedN, deadline, name]);
  const debounced = useDebounced(planReq, 350);
  const plan = useGoalPlan(isNew || existing ? debounced : null);
  const emoji = KINDS.find((k) => k.kind === kind)?.emoji ?? '🎯';

  const submit = () => {
    if (!name.trim() || targetN <= 0) return;
    const body = { name: name.trim(), target_amount: targetN, saved_amount: savedN, deadline, kind, emoji };
    const done = () => {
      haptic.success();
      toast(isNew ? t('w.goalplan.created') : t('goals.saved_ok'), 'good');
      onClose();
    };
    const fail = (e: unknown) => toast(e instanceof Error ? e.message : t('common.error'), 'warn');
    if (isNew) create.mutate(body, { onSuccess: done, onError: fail });
    else if (existing) update.mutate({ goalId: existing.id, patch: body }, { onSuccess: done, onError: fail });
  };

  const onDelete = async () => {
    if (!existing) return;
    const ok = await confirmAsync(t('goals.deleteConfirm'), t('common.delete'), t('common.cancel'));
    if (!ok) return;
    remove.mutate(existing.id, {
      onSuccess: () => {
        haptic.warning();
        toast(t('goals.deleted'));
        onClose();
      },
    });
  };

  const p = plan.data;
  const feasColor = p ? (p.feasibility === 'on_track' ? c.good : p.feasibility === 'stretch' ? c.amber : c.warn) : c.textMuted;

  return (
    <Sheet
      visible={!!goal}
      onClose={onClose}
      title={isNew ? t('goals.new') : t('goals.edit')}
      footer={
        <View style={{ gap: 8 }}>
          <Button label={isNew ? t('goals.create') : t('common.save')} icon={isNew ? 'target' : 'check'} onPress={submit} disabled={!name.trim() || targetN <= 0} loading={create.isPending || update.isPending} full />
          {existing ? <Button label={t('common.delete')} variant="danger" icon="trash" onPress={onDelete} loading={remove.isPending} full /> : null}
        </View>
      }
    >
      <Field label={t('goals.name')}>
        <TextInput value={name} onChangeText={setName} placeholder={t('goals.namePlaceholder')} placeholderTextColor={c.textFaint} style={s.input} maxLength={40} />
      </Field>
      <Field label={t('goals.kind')}>
        <View style={s.wrapRow}>
          {KINDS.map((k) => (
            <Chip key={k.kind} label={`${k.emoji} ${t(`goals.kind.${k.kind}` as TKey)}`} selected={kind === k.kind} onPress={() => setKind(k.kind)} small />
          ))}
        </View>
      </Field>
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <View style={{ flex: 1 }}>
          <Field label={t('goals.target')}>
            <TextInput value={target} onChangeText={setTarget} keyboardType="numeric" inputMode="decimal" placeholder="2000" placeholderTextColor={c.textFaint} style={s.input} />
          </Field>
        </View>
        <View style={{ flex: 1 }}>
          <Field label={t('goals.saved')}>
            <TextInput value={saved} onChangeText={setSaved} keyboardType="numeric" inputMode="decimal" placeholder="0" placeholderTextColor={c.textFaint} style={s.input} />
          </Field>
        </View>
      </View>
      {existing ? (
        <Field label={t('goals.addSavings')}>
          <View style={s.wrapRow}>
            {[25, 50, 100, 250].map((a) => (
              <Chip key={a} label={`+${money(a)}`} onPress={() => setSaved(String(savedN + a))} small />
            ))}
          </View>
        </Field>
      ) : null}
      <Field label={t('goals.deadline')}>
        <View style={s.wrapRow}>
          {MONTH_OPTIONS.map((m) => (
            <Chip key={m} label={t('common.months', { n: m })} selected={months === m} onPress={() => setMonths(m)} small />
          ))}
          {months && !MONTH_OPTIONS.includes(months) ? <Chip label={t('common.months', { n: months })} selected small /> : null}
          <Chip label={t('goals.noDeadline')} selected={months === null} onPress={() => setMonths(null)} small />
        </View>
      </Field>

      {/* Live plan preview */}
      {planReq ? (
        <View style={[s.preview, { borderColor: `${feasColor}55` }]}>
          <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
            <Text variant="micro" tone="muted">
              {t('goals.preview').toUpperCase()} {plan.isFetching ? '…' : ''}
            </Text>
            {p ? <Pill label={t(`w.goalplan.${p.feasibility}` as TKey)} color={feasColor} /> : null}
          </View>
          {p ? (
            <>
              <View style={{ flexDirection: 'row', gap: 12 }}>
                <PreviewStat label={t('w.goalplan.needed')} value={money(p.needed_per_month)} />
                <PreviewStat label={t('w.goalplan.surplus')} value={money(p.current_monthly_surplus)} />
                <PreviewStat label={t('w.goalplan.gap')} value={money(p.gap)} color={p.gap > 0 ? c.warn : c.good} />
              </View>
              {p.cuts.slice(0, 3).map((cut) => (
                <Text key={cut.label} variant="caption" tone="muted">
                  💧 {cut.label} −{cut.cut_pct}% → +{money(cut.monthly_saving)}
                  {t('common.perMonth')}
                </Text>
              ))}
              <Text variant="caption">{p.summary}</Text>
              {p.suggested_deadline ? (
                <Text variant="caption" weight="700" tone="amber">
                  {t('w.goalplan.suggested', { date: date(p.suggested_deadline, true) })}
                </Text>
              ) : null}
            </>
          ) : (
            <Skeleton height={60} />
          )}
        </View>
      ) : null}
    </Sheet>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: 6 }}>
      <Text variant="caption" weight="700" tone="muted">
        {label}
      </Text>
      {children}
    </View>
  );
}

function PreviewStat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <View style={{ flex: 1, gap: 2 }}>
      <Text variant="micro" tone="muted" numberOfLines={1}>
        {label.toUpperCase()}
      </Text>
      <Text variant="callout" weight="800" money color={color} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  addBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: t.c.primary, alignItems: 'center', justifyContent: 'center' },
  summary: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  goal: { gap: 12 },
  goalTop: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  goalBottom: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  input: {
    height: 48,
    borderRadius: 14,
    paddingHorizontal: 14,
    backgroundColor: t.c.surface,
    borderWidth: 1,
    borderColor: t.c.border,
    color: t.c.text,
    fontSize: 16,
    fontFamily,
    fontVariant: ['tabular-nums'],
  },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  preview: { gap: 8, padding: 14, borderRadius: 18, borderWidth: 1, backgroundColor: t.c.surface },
}));
