/**
 * The three-basket meter — SPankkiBot's core teaching device (SPEC §2).
 *
 * One horizontal bar split into fixed / irregular / leak, with a legend that
 * expands on tap to explain *why* a basket exists and what is in it this month.
 * Used on Home (this month) and as the `basket_breakdown` chat widget, so the
 * same mental model appears wherever money is discussed.
 */
import { useState } from 'react';
import { View } from 'react-native';
import Animated, { FadeIn, LinearTransition } from 'react-native-reanimated';

import type { BasketKey, LabelTotal } from '@/api/types';
import { useEntrance } from '@/components/charts/useTween';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { Icon } from '@/components/ui/Icon';
import { useT, type TKey } from '@/i18n';
import { makeStyles, useTheme } from '@/theme';

const ORDER: BasketKey[] = ['fixed', 'irregular', 'leak'];
const EMOJI: Record<BasketKey, string> = { fixed: '🏠', irregular: '🧰', leak: '💧' };

type Props = {
  values: Record<BasketKey, number>;
  explanations?: Partial<Record<BasketKey, string>>;
  top?: Partial<Record<BasketKey, LabelTotal[]>>;
  initiallyOpen?: BasketKey | null;
  /** Home only: tag each bar segment so tests can find it exactly once. */
  segmentTestIDs?: boolean;
};

export function BasketMeter({ values, explanations, top, initiallyOpen = null, segmentTestIDs = false }: Props) {
  const s = useStyles();
  const { c } = useTheme();
  const { t, money, pct } = useT();
  const [open, setOpen] = useState<BasketKey | null>(initiallyOpen);
  const p = useEntrance(800, [values.fixed, values.irregular, values.leak]);
  const total = ORDER.reduce((a, k) => a + Math.max(0, values[k] ?? 0), 0) || 1;
  return (
    <View style={s.wrap}>
      <View style={s.bar} accessibilityRole="image" accessibilityLabel={ORDER.map((k) => `${t(`basket.${k}` as TKey)} ${pct(values[k] / total)}`).join(', ')}>
        {ORDER.map((k, i) => {
          const share = Math.max(0, values[k]) / total;
          return <View key={k} testID={segmentTestIDs ? `basket-segment-${k}` : undefined} style={{ flex: Math.max(0.0001, share * p), backgroundColor: c.basket[k], marginLeft: i ? 2 : 0 }} />;
        })}
        <View style={{ flex: Math.max(0.0001, 1 - p) }} />
      </View>
      {ORDER.map((k) => {
        const isOpen = open === k;
        const items = top?.[k] ?? [];
        return (
          <Animated.View key={k} layout={LinearTransition.springify().damping(18)}>
            <PressableScale
              scaleTo={0.985}
              onPress={() => setOpen(isOpen ? null : k)}
              style={[s.row, isOpen && { backgroundColor: `${c.basket[k]}14`, borderColor: `${c.basket[k]}44` }]}
              accessibilityState={{ expanded: isOpen }}
              accessibilityLabel={`${t(`basket.${k}` as TKey)}, ${money(values[k])}`}
            >
              <View style={s.rowHead}>
                <View style={[s.swatch, { backgroundColor: `${c.basket[k]}26` }]}>
                  <Text variant="callout">{EMOJI[k]}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text variant="callout" weight="600" numberOfLines={1}>
                    {t(`basket.${k}` as TKey)}
                  </Text>
                  <Text variant="caption" tone="muted">
                    {pct(values[k] / total)}
                  </Text>
                </View>
                <Text variant="callout" weight="700" money>
                  {money(values[k])}
                </Text>
                <Icon name={isOpen ? 'chevronDown' : 'chevronRight'} size={16} color={c.textFaint} />
              </View>
              {isOpen ? (
                <Animated.View entering={FadeIn.duration(220)} style={s.detail}>
                  {explanations?.[k] ? (
                    <Text variant="caption" tone="muted">
                      {explanations[k]}
                    </Text>
                  ) : null}
                  {items.slice(0, 4).map((it) => (
                    <View key={it.label} style={s.item}>
                      <View style={[s.dot, { backgroundColor: c.basket[k] }]} />
                      <Text variant="caption" style={{ flex: 1 }} numberOfLines={1}>
                        {it.label}
                      </Text>
                      <Text variant="caption" weight="700" money>
                        {money(it.total)}
                      </Text>
                    </View>
                  ))}
                </Animated.View>
              ) : null}
            </PressableScale>
          </Animated.View>
        );
      })}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: 8 },
  bar: { flexDirection: 'row', height: 14, borderRadius: 7, overflow: 'hidden', backgroundColor: t.c.surfaceStrong, marginBottom: 6 },
  row: { borderRadius: 16, padding: 10, borderWidth: 1, borderColor: 'transparent', gap: 8 },
  rowHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  swatch: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  detail: { gap: 6, paddingLeft: 46 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 6, height: 6, borderRadius: 3 },
}));
