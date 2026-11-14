/**
 * "Safe to spend today" — turns a misleading balance into one actionable daily
 * number (balance − bills before payday − buffer). Colour encodes status.
 */
import { View } from 'react-native';

import type { SafeToSpend } from '@/api/types';
import { AnimatedMoney } from '@/components/ui/AnimatedMoney';
import { GlassCard } from '@/components/ui/GlassCard';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { Text } from '@/components/ui/Text';
import { statusColor } from '@/components/widgets/SafeToSpendWidget';
import { Pill } from '@/components/widgets/WidgetCard';
import { useT, type TKey } from '@/i18n';
import { openChat } from '@/lib/chatNav';
import { useTheme } from '@/theme';

export function SafeToSpendCard({ data }: { data: SafeToSpend }) {
  const { c } = useTheme();
  const { t, money } = useT();
  const color = statusColor(c, data.status);
  const cycle = Math.max(0, Math.min(1, 1 - data.days_until_payday / 30));
  return (
    <GlassCard testID="safe-to-spend-card" tint={color} onPress={() => openChat(t('chat.starter3'))} accessibilityLabel={`${t('home.safeToday')} ${money(data.safe_per_day)}`}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <Text variant="caption" tone="muted" style={{ flex: 1 }}>
          {t('home.safeToday')}
        </Text>
        <Pill label={t(`home.status.${data.status}` as TKey)} color={color} />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 4, gap: 8 }}>
        <AnimatedMoney testID="safe-to-spend-amount" value={data.safe_per_day} variant="hero" weight="800" color={color} />
        <Text variant="callout" weight="600" tone="muted" style={{ marginBottom: 6 }} money>
          {t('home.safeWeek', { amount: money(data.safe_this_week) })}
        </Text>
      </View>
      <View style={{ marginTop: 12, gap: 6 }}>
        <ProgressBar value={cycle} color={color} height={5} />
        <Text variant="caption" tone="muted">
          💼 {data.days_until_payday <= 1 ? t('home.paydayTomorrow') : t('home.payday', { n: data.days_until_payday })}
        </Text>
      </View>
    </GlassCard>
  );
}
