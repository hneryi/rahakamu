/** Home hero card: balance, 30-day sparkline, and this month's in / out / saved. */
import { View } from 'react-native';

import type { Overview } from '@/api/types';
import { Sparkline } from '@/components/charts/Sparkline';
import { AnimatedMoney } from '@/components/ui/AnimatedMoney';
import { GlassCard } from '@/components/ui/GlassCard';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { openChat } from '@/lib/chatNav';
import { makeStyles, useTheme } from '@/theme';

export function BalanceCard({ data }: { data: Overview }) {
  const s = useStyles();
  const { c } = useTheme();
  const { t, money, date } = useT();
  const values = data.trend_30d.map((p) => p.balance);
  const negative = data.balance < 0;
  return (
    <GlassCard testID="balance-card" onPress={() => openChat(t('home.askBalance'))} accessibilityLabel={`${t('home.balance')} ${money(data.balance)}`}>
      <View style={s.top}>
        <Text variant="caption" tone="muted">
          {t('home.balance')}
        </Text>
        <Text variant="micro" tone="faint">
          {t('home.asOf', { date: date(data.as_of, true) })}
        </Text>
      </View>
      <AnimatedMoney testID="balance-amount" value={data.balance} variant="hero" weight="800" color={negative ? c.warn : c.text} decimals={2} />
      <View style={{ marginTop: 6, marginHorizontal: -4 }}>
        <Sparkline values={values} color={negative ? c.warn : c.primary} showZero />
      </View>
      <View style={s.row}>
        <Mini label={t('home.income')} value={money(data.month.income)} color={c.good} />
        <Mini label={t('home.spent')} value={money(data.month.spent)} color={c.text} />
        <Mini label={t('home.saved')} value={money(data.month.saved)} color={c.accent} />
      </View>
    </GlassCard>
  );
}

function Mini({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={{ flex: 1, gap: 1 }}>
      <Text variant="micro" tone="muted">
        {label.toUpperCase()}
      </Text>
      <Text variant="callout" weight="700" money color={color} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
    </View>
  );
}

const useStyles = makeStyles(() => ({
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  row: { flexDirection: 'row', gap: 12, marginTop: 10 },
}));
