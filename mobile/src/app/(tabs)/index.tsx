/**
 * HOME — the hero screen (SPEC §5.2).
 *
 * Answers the three questions people actually open a bank app for, top to
 * bottom: "How much do I have?" (balance), "How much can I spend?" (safe to
 * spend today), "Am I getting anywhere?" (goals) — then shows the evidence
 * (recent transactions) and teaches *where* the money went with the
 * three-basket meter. The coach is always one tap / one hold away in the dock.
 */
import { router } from 'expo-router';
import { useMemo } from 'react';
import { View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { useBaskets, useOverview } from '@/api/hooks';
import { BalanceCard } from '@/components/home/BalanceCard';
import { BasketMeter } from '@/components/home/BasketMeter';
import { CharacterDock } from '@/components/home/CharacterDock';
import { GoalCarousel } from '@/components/home/GoalCarousel';
import { SafeToSpendCard } from '@/components/home/SafeToSpendCard';
import { TxRow } from '@/components/home/TxRow';
import { DemoBadge } from '@/components/ui/DemoBadge';
import { GlassCard } from '@/components/ui/GlassCard';
import { Icon } from '@/components/ui/Icon';
import { PressableScale } from '@/components/ui/PressableScale';
import { Screen } from '@/components/ui/Screen';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { Skeleton } from '@/components/ui/Skeleton';
import { ErrorState } from '@/components/ui/States';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { useSession } from '@/store/session';
import { layout, makeStyles, useTheme } from '@/theme';

export default function HomeScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { t, date } = useT();
  const name = useSession((st) => st.customerName);
  const overview = useOverview();
  const baskets = useBaskets(6);
  const data = overview.data;

  const enter = (i: number) => FadeInDown.delay(60 * i).springify().damping(18);

  const header = useMemo(
    () => (
      <View style={s.greeting}>
        <View style={{ flex: 1, gap: 2 }}>
          <Text testID="home-greeting" variant="title" weight="800" numberOfLines={1}>
            {t('home.greeting', { name: data?.customer.name ?? name ?? '' })} 👋
          </Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text variant="caption" tone="muted">
              {data ? date(data.as_of, true) : ' '}
            </Text>
            <DemoBadge />
          </View>
        </View>
        <PressableScale testID="settings-button" onPress={() => router.push('/settings')} style={s.avatar} accessibilityLabel={t('set.title')}>
          <Icon name="settings" size={20} color={c.text} />
        </PressableScale>
      </View>
    ),
    [s, t, data, name, date, c.text],
  );

  return (
    <View style={{ flex: 1 }} testID="home-screen">
      <Screen header={header} bottomExtra={layout.dockHeight - 40} onRefresh={() => overview.refetch()} refreshing={overview.isRefetching}>
        {overview.isError && !data ? <ErrorState onRetry={() => overview.refetch()} /> : null}
        {!data && !overview.isError ? (
          <View style={{ gap: 16 }}>
            <Skeleton height={180} radius={24} />
            <Skeleton height={130} radius={24} />
            <Skeleton height={150} radius={24} />
          </View>
        ) : null}
        {data ? (
          <>
            <Animated.View entering={enter(0)}>
              <BalanceCard data={data} />
            </Animated.View>
            <Animated.View entering={enter(1)}>
              <SafeToSpendCard data={data.safe_to_spend} />
            </Animated.View>
            <Animated.View entering={enter(2)}>
              <SectionHeader title={t('home.goals')} action={{ label: t('common.seeAll'), onPress: () => router.navigate('/goals') }} />
              <GoalCarousel goals={data.goals} />
            </Animated.View>
            <Animated.View entering={enter(3)}>
              <SectionHeader title={t('home.recent')} action={{ label: t('common.seeAll'), onPress: () => router.navigate('/insights') }} />
              <GlassCard testID="recent-transactions" style={{ paddingVertical: 6 }}>
                {data.recent_transactions.slice(0, 8).map((tx) => (
                  <TxRow key={tx.id} tx={tx} />
                ))}
              </GlassCard>
            </Animated.View>
            <Animated.View entering={enter(4)}>
              <SectionHeader title={t('home.baskets')} subtitle={t('home.basketsHint')} askPrompt={t('ins.ask.categories')} />
              <GlassCard testID="basket-meter">
                <BasketMeter segmentTestIDs values={data.month.by_basket} explanations={baskets.data?.explanations} top={baskets.data?.current_month.top} />
              </GlassCard>
            </Animated.View>
          </>
        ) : null}
      </Screen>
      <CharacterDock nudges={data?.nudges ?? []} />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  greeting: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 4 },
  avatar: { width: 44, height: 44, borderRadius: 22, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.surface, borderWidth: 1, borderColor: t.c.border },
}));
