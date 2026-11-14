/**
 * `benchmark` widget (+ frameless view for Insights): you vs peers in your age
 * group (p25–p75 band, median tick) and Statistics Finland averages (diamond).
 * Benchmarks answer "is this normal?" — a question people rarely ask out loud.
 */
import { useState } from 'react';
import { Linking, View } from 'react-native';

import type { Benchmarks } from '@/api/types';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { categoryLabel } from '@/i18n/categories';
import { useTheme } from '@/theme';
import { WidgetCard } from './WidgetCard';

export function BenchmarkView({ data, limit }: { data: Benchmarks; limit?: number }) {
  const { c } = useTheme();
  const { t, money, locale } = useT();
  const [showSources, setShowSources] = useState(false);
  const rows = (data.categories ?? []).slice(0, limit ?? 8);
  return (
    <View style={{ gap: 14 }}>
      <Text variant="caption" tone="muted">
        {data.peer_group?.label} · n = {data.peer_group?.size}
      </Text>
      {rows.map((r) => {
        const max = Math.max(r.you_monthly, r.peer_p75, r.stat_fi_monthly ?? 0, 1) * 1.1;
        const X = (v: number) => `${Math.min(100, (v / max) * 100)}%` as const;
        const above = r.you_monthly > r.peer_p75;
        const youColor = above ? c.basket.leak : r.you_monthly < r.peer_p25 ? c.good : c.text;
        return (
          <View key={r.category} style={{ gap: 6 }}>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}>
              <Text variant="callout" weight="600">
                {categoryLabel(locale, r.category)}
              </Text>
              <Text variant="callout" weight="800" money color={youColor}>
                {money(r.you_monthly)}
                <Text variant="caption" tone="muted">
                  {' '}
                  / {money(r.peer_median_monthly)}
                </Text>
              </Text>
            </View>
            <View style={{ height: 14, justifyContent: 'center' }}>
              <View style={{ height: 6, borderRadius: 3, backgroundColor: c.surfaceStrong }} />
              <View style={{ position: 'absolute', left: X(r.peer_p25), width: `${Math.max(1, ((r.peer_p75 - r.peer_p25) / max) * 100)}%`, height: 6, borderRadius: 3, backgroundColor: `${c.accent}55` }} />
              <View style={{ position: 'absolute', left: X(r.peer_median_monthly), width: 2, height: 14, marginLeft: -1, backgroundColor: c.accent }} />
              {r.stat_fi_monthly ? (
                <View style={{ position: 'absolute', left: X(r.stat_fi_monthly), width: 9, height: 9, marginLeft: -4.5, transform: [{ rotate: '45deg' }], backgroundColor: c.amber }} />
              ) : null}
              <View style={{ position: 'absolute', left: X(r.you_monthly), width: 14, height: 14, marginLeft: -7, borderRadius: 7, backgroundColor: youColor, borderWidth: 2, borderColor: c.bgSolid }} />
            </View>
            <Text variant="caption" tone="faint">
              {t('w.bench.percentile', { n: Math.round(r.percentile) })}
            </Text>
          </View>
        );
      })}
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
        <Legend color={c.text} round label={t('common.you')} />
        <Legend color={c.accent} label={t('w.bench.median')} />
        <Legend color={`${c.accent}55`} label={t('w.bench.range')} />
        <Legend color={c.amber} diamond label={t('w.bench.statfi')} />
      </View>
      {data.sources?.length ? (
        <View style={{ gap: 4 }}>
          <Text variant="caption" weight="700" tone="primary" onPress={() => setShowSources((v) => !v)}>
            {t('w.bench.sources')} {showSources ? '▲' : '▼'}
          </Text>
          {showSources
            ? data.sources.map((s) => (
                <Text key={s.name} variant="caption" tone="muted" onPress={() => s.url && Linking.openURL(s.url).catch(() => {})}>
                  • {s.name} — {s.note}
                </Text>
              ))
            : null}
        </View>
      ) : null}
    </View>
  );
}

function Legend({ color, label, round, diamond }: { color: string; label: string; round?: boolean; diamond?: boolean }) {
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
      <View style={{ width: 10, height: round ? 10 : diamond ? 8 : 6, borderRadius: round ? 5 : 2, backgroundColor: color, transform: diamond ? [{ rotate: '45deg' }] : undefined }} />
      <Text variant="micro" tone="muted">
        {label}
      </Text>
    </View>
  );
}

export function BenchmarkWidget({ data }: { data: Benchmarks }) {
  const { t } = useT();
  return (
    <WidgetCard title={t('w.bench.title')} emoji="👥">
      <BenchmarkView data={data} limit={6} />
    </WidgetCard>
  );
}
