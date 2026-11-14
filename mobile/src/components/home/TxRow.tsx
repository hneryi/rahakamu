/**
 * One transaction row: emoji icon, friendly merchant label ("Café #12"),
 * category + date, a coloured basket dot (the three-basket model is visible even
 * in the transaction list) and the amount (income in green).
 */
import { View } from 'react-native';

import type { Tx } from '@/api/types';
import { Text } from '@/components/ui/Text';
import { useT, type TKey } from '@/i18n';
import { makeStyles, useTheme } from '@/theme';

export function TxRow({ tx, compact }: { tx: Tx; compact?: boolean }) {
  const s = useStyles();
  const { c } = useTheme();
  const { money, date, t } = useT();
  const basketColor = c.basket[tx.basket] ?? c.textMuted;
  const income = tx.amount > 0;
  return (
    <View testID={`tx-row-${tx.id}`} style={[s.row, compact && s.compact]} accessible accessibilityLabel={`${tx.merchant_label}, ${money(tx.amount)}, ${date(tx.date)}`}>
      <View style={s.icon}>
        <Text variant="body">{tx.icon || '💳'}</Text>
      </View>
      <View style={s.mid}>
        <Text variant="callout" weight="600" numberOfLines={1}>
          {tx.merchant_label}
        </Text>
        <View style={s.meta}>
          <View style={[s.dot, { backgroundColor: basketColor }]} />
          <Text variant="caption" tone="muted" numberOfLines={1} style={{ flexShrink: 1 }}>
            {t(`basket.${tx.basket}${tx.basket === 'income' || tx.basket === 'saving' ? '' : '.short'}` as TKey)} · {date(tx.date)}
          </Text>
        </View>
      </View>
      <Text variant="callout" weight="700" money color={income ? c.good : c.text}>
        {money(tx.amount, { sign: true })}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 9 },
  compact: { paddingVertical: 6 },
  icon: { width: 40, height: 40, borderRadius: 14, backgroundColor: t.c.surfaceStrong, alignItems: 'center', justifyContent: 'center' },
  mid: { flex: 1, gap: 2, minWidth: 0 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4 },
}));
