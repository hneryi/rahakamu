/**
 * `what_if` widget — interactive scenario simulator. Dragging the slider
 * re-calls POST /what-if (debounced 250 ms) so the user *feels* how a small
 * habit change compounds over a year. Optimistic local estimate keeps the
 * numbers moving instantly while the server answer is in flight.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { View } from 'react-native';

import { useWhatIf } from '@/api/hooks';
import type { WhatIfData, WhatIfResult } from '@/api/types';
import { LineChart } from '@/components/charts/LineChart';
import { AnimatedMoney } from '@/components/ui/AnimatedMoney';
import { Slider } from '@/components/ui/Slider';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { categoryLabel } from '@/i18n/categories';
import { useTheme } from '@/theme';
import { WidgetCard } from './WidgetCard';

export function WhatIfWidget({ data }: { data: WhatIfData }) {
  const { c } = useTheme();
  const { t, money, locale } = useT();
  const slider = data.slider ?? { min: -100, max: 0, value: -20 };
  const [value, setValue] = useState(slider.value);
  const [result, setResult] = useState<WhatIfResult>(data.result);
  const mutation = useWhatIf();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const returnPct = data.invest_return_pct ?? data.result.invest_return_pct ?? 0;
  const target =
    (result.per_item?.[0]?.label ? categoryLabel(locale, result.per_item[0].label) : null) ??
    (slider.category ? categoryLabel(locale, slider.category) : slider.basket ? t(`basket.${slider.basket}` as TKey) : categoryLabel(locale, data.base_adjustments?.[0]?.category));

  // Instant local estimate: scale the last server result linearly by the slider.
  const estimate = useMemo(() => {
    const base = result.baseline_monthly;
    const monthly = (base * -value) / 100;
    return { monthly, total: monthly * result.horizon_months };
  }, [value, result]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  const onChange = (v: number) => {
    setValue(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const adj = {
        ...(slider.category ? { category: slider.category } : {}),
        ...(slider.basket ? { basket: slider.basket } : {}),
        ...(slider.merchant ? { merchant: slider.merchant } : {}),
        change_pct: v,
      };
      mutation.mutate(
        { adjustments: data.base_adjustments?.length > 1 ? [adj, ...data.base_adjustments.slice(1)] : [adj], horizon_months: result.horizon_months, invest_return_pct: returnPct },
        { onSuccess: (r) => setResult(r) },
      );
    }, 250);
  };

  const series = (result.series ?? []).map((p) => ({ x: `${p.month}`, y: p.cumulative }));

  return (
    <WidgetCard title={`${t('w.whatif.title')} ${target}`} emoji="🎚️" tint={c.accent}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text variant="callout" tone="muted">
          {t('w.whatif.change')}
        </Text>
        <Text variant="title" weight="800" money color={c.accent}>
          {value}%
        </Text>
      </View>
      <Slider min={slider.min ?? -100} max={slider.max ?? 0} step={5} value={value} onChange={onChange} color={c.accent} accessibilityLabel={`${t('w.whatif.change')} ${target}`} />
      <View style={{ flexDirection: 'row', gap: 12 }}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text variant="micro" tone="muted">
            {t('w.whatif.monthly').toUpperCase()}
          </Text>
          <AnimatedMoney value={estimate.monthly} variant="title" weight="800" color={c.good} duration={250} />
        </View>
        <View style={{ flex: 1, gap: 2 }}>
          <Text variant="micro" tone="muted">
            {t('w.whatif.year', { n: result.horizon_months }).toUpperCase()}
          </Text>
          <AnimatedMoney value={estimate.total} variant="title" weight="800" color={c.good} duration={250} />
        </View>
      </View>
      <Text variant="caption" tone="faint">
        {t('w.whatif.baseline', { amount: money(result.baseline_monthly), next: money(result.baseline_monthly + (result.baseline_monthly * value) / 100) })}
      </Text>
      {series.length > 1 ? <LineChart points={series} unit="€" height={140} color={c.good} /> : null}
      {result.with_return > result.total_saving + 1 ? (
        <Text variant="caption" tone="muted">
          {t('w.whatif.withReturn')}: {money(result.with_return)}
        </Text>
      ) : null}
    </WidgetCard>
  );
}
