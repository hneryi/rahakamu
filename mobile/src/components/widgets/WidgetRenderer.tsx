/**
 * Generative-UI renderer (SPEC §5.3).
 *
 * The agent's tools emit typed widgets over SSE; this maps `type` → component.
 * Two safety properties matter for model-generated UI:
 * 1. **Forward compatibility** — an unknown type renders a small, tidy
 *    placeholder, so the backend can ship new widgets before the app knows them.
 * 2. **Isolation** — each widget sits in its own error boundary; a malformed
 *    payload turns that one card into the same placeholder instead of crashing
 *    the conversation.
 *
 * One primary action per answer: when a `goal_plan` and an `action_buttons`
 * widget arrive together, the plan's own "Create this goal" button takes the
 * backend's create payload and the duplicate button is dropped.
 */
import type { ComponentType } from 'react';
import { View } from 'react-native';

import type { GoalCreate, Widget, WidgetDataMap, WidgetType } from '@/api/types';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { useTheme } from '@/theme';
import { ActionButtonsWidget } from './ActionButtonsWidget';
import { BarChartWidget } from './BarChartWidget';
import { BasketBreakdownWidget } from './BasketBreakdownWidget';
import { BenchmarkWidget } from './BenchmarkWidget';
import { DonutChartWidget } from './DonutChartWidget';
import { GoalPlanWidget } from './GoalPlanWidget';
import { HomeReadinessWidget } from './HomeReadinessWidget';
import { KpiWidget } from './KpiWidget';
import { LessonWidget } from './LessonWidget';
import { LineChartWidget } from './LineChartWidget';
import { SafeToSpendWidget } from './SafeToSpendWidget';
import { SpenderProfileWidget } from './SpenderProfileWidget';
import { SurvivalPlanWidget } from './SurvivalPlanWidget';
import { TransactionListWidget } from './TransactionListWidget';
import { WhatIfWidget } from './WhatIfWidget';

const REGISTRY: { [K in WidgetType]: ComponentType<{ data: WidgetDataMap[K] }> } = {
  kpi: KpiWidget,
  bar_chart: BarChartWidget,
  line_chart: LineChartWidget,
  donut_chart: DonutChartWidget,
  basket_breakdown: BasketBreakdownWidget,
  safe_to_spend: SafeToSpendWidget,
  goal_plan: GoalPlanWidget,
  what_if: WhatIfWidget,
  transaction_list: TransactionListWidget,
  spender_profile: SpenderProfileWidget,
  benchmark: BenchmarkWidget,
  survival_plan: SurvivalPlanWidget,
  home_readiness: HomeReadinessWidget,
  lesson: LessonWidget,
  action_buttons: ActionButtonsWidget,
};

export const isKnownWidget = (type: string): type is WidgetType => Object.prototype.hasOwnProperty.call(REGISTRY, type);

function UnknownWidget() {
  const { c } = useTheme();
  const { t } = useT();
  return (
    <View
      testID="unknown-widget"
      style={{ paddingVertical: 10, paddingHorizontal: 14, borderRadius: 16, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface }}
    >
      <Text variant="caption" tone="muted">
        {t('w.unknown')}
      </Text>
    </View>
  );
}

/** The backend's own create-goal payload, when the answer carries one. */
function createGoalPayload(siblings: Widget[] | undefined): GoalCreate | undefined {
  for (const w of siblings ?? []) {
    if (w.type !== 'action_buttons') continue;
    const buttons = (w.data as WidgetDataMap['action_buttons'] | undefined)?.buttons;
    if (!Array.isArray(buttons)) continue;
    for (const b of buttons) {
      if (b?.kind === 'create_goal' && b.payload && typeof b.payload === 'object') return b.payload;
    }
  }
  return undefined;
}

export function WidgetRenderer({ widget, siblings }: { widget: Widget; siblings?: Widget[] }) {
  if (!isKnownWidget(widget.type) || !widget.data || typeof widget.data !== 'object') return <UnknownWidget />;
  const hasPlan = (siblings ?? []).some((w) => w.type === 'goal_plan');

  let body: React.ReactNode;
  if (widget.type === 'goal_plan') {
    body = <GoalPlanWidget data={widget.data as WidgetDataMap['goal_plan']} createPayload={createGoalPayload(siblings)} />;
  } else if (widget.type === 'action_buttons') {
    const data = widget.data as WidgetDataMap['action_buttons'];
    const buttons = Array.isArray(data.buttons) ? data.buttons : [];
    const rest = hasPlan ? buttons.filter((b) => b?.kind !== 'create_goal') : buttons;
    if (rest.length === 0) return null;
    body = <ActionButtonsWidget data={{ ...data, buttons: rest }} secondaryOnly={hasPlan} />;
  } else {
    const Comp = REGISTRY[widget.type] as ComponentType<{ data: unknown }>;
    body = <Comp data={widget.data} />;
  }

  return (
    <ErrorBoundary fallback={<UnknownWidget />}>
      <View testID={`widget-${widget.type}`}>{body}</View>
    </ErrorBoundary>
  );
}
