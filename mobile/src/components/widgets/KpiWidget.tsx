/** `kpi` widget: 1–4 headline numbers with optional delta and good/bad tone. */
import { View } from 'react-native';

import type { KpiData } from '@/api/types';
import { AnimatedMoney } from '@/components/ui/AnimatedMoney';
import { GlassCard } from '@/components/ui/GlassCard';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { useTheme } from '@/theme';

export function KpiWidget({ data }: { data: KpiData }) {
  const { c } = useTheme();
  const { num, pct } = useT();
  const items = data.items ?? [];
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
      {items.map((it, i) => {
        const color = it.tone === 'good' ? c.good : it.tone === 'bad' ? c.warn : c.text;
        return (
          <GlassCard key={`${it.label}-${i}`} style={{ flexGrow: 1, flexBasis: items.length === 1 ? '100%' : '45%', gap: 4 }}>
            <Text variant="micro" tone="muted" numberOfLines={2}>
              {it.label.toUpperCase()}
            </Text>
            {it.unit === '€' ? (
              <AnimatedMoney value={it.value} variant="title" weight="800" color={color} />
            ) : (
              <Text variant="title" weight="800" money color={color}>
                {it.unit === '%' ? pct(it.value > 1 ? it.value / 100 : it.value) : num(it.value, 1)}
              </Text>
            )}
            {typeof it.delta === 'number' ? (
              <Text variant="caption" weight="700" color={it.delta > 0 ? (it.tone === 'good' ? c.good : c.warn) : it.tone === 'bad' ? c.warn : c.good}>
                {it.delta > 0 ? '▲' : '▼'} {num(Math.abs(it.delta), 1)}
                {it.unit === '%' ? ' pp' : it.unit === '€' ? ' €' : ''}
              </Text>
            ) : null}
          </GlassCard>
        );
      })}
    </View>
  );
}
