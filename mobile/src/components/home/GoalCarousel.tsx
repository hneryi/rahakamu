/** Horizontal goal cards with progress rings; the last card creates a new goal. */
import { router } from 'expo-router';
import { ScrollView, View } from 'react-native';
import Animated, { FadeInRight } from 'react-native-reanimated';

import type { Goal } from '@/api/types';
import { ProgressRing } from '@/components/charts/ProgressRing';
import { GlassCard } from '@/components/ui/GlassCard';
import { Icon } from '@/components/ui/Icon';
import { Text } from '@/components/ui/Text';
import { useT } from '@/i18n';
import { openChat } from '@/lib/chatNav';
import { makeStyles, useTheme } from '@/theme';

export function GoalCarousel({ goals }: { goals: Goal[] }) {
  const s = useStyles();
  const { c } = useTheme();
  const { t, money, date } = useT();
  return (
    <ScrollView testID="goal-carousel" horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.row} style={s.scroller}>
      {goals.map((g, i) => {
        const left = Math.max(0, g.target_amount - g.saved_amount);
        const done = g.progress >= 1;
        return (
          <Animated.View key={g.id} entering={FadeInRight.delay(i * 70).springify().damping(18)}>
            <GlassCard testID={`goal-card-${g.id}`} style={s.card} onPress={() => openChat(t('goals.ask', { name: g.name }))} accessibilityLabel={`${g.name}, ${Math.round(g.progress * 100)}%`}>
              <ProgressRing progress={g.progress} size={58} stroke={6} color={done ? c.good : c.primary}>
                <Text variant="title">{g.emoji}</Text>
              </ProgressRing>
              <Text variant="callout" weight="700" numberOfLines={1}>
                {g.name}
              </Text>
              <Text variant="caption" weight="700" money tone={done ? 'good' : 'text'}>
                {done ? t('home.goalDone') : t('home.goalLeft', { amount: money(left) })}
              </Text>
              <Text variant="micro" tone="muted" numberOfLines={1}>
                {Math.round(g.progress * 100)}%{g.deadline ? ` · ${date(g.deadline, true)}` : ''}
              </Text>
            </GlassCard>
          </Animated.View>
        );
      })}
      <GlassCard style={[s.card, s.add]} onPress={() => router.navigate({ pathname: '/goals', params: { new: '1' } })} accessibilityLabel={t('home.newGoal')}>
        <View style={s.plus}>
          <Icon name="plus" size={26} color={c.primary} />
        </View>
        <Text variant="callout" weight="700" tone="primary">
          {t('home.newGoal')}
        </Text>
      </GlassCard>
    </ScrollView>
  );
}

const useStyles = makeStyles((t) => ({
  scroller: { marginHorizontal: -16 },
  row: { gap: 12, paddingHorizontal: 16 },
  card: { width: 158, gap: 6 },
  add: { alignItems: 'center', justifyContent: 'center', borderStyle: 'dashed' },
  plus: { width: 58, height: 58, borderRadius: 29, backgroundColor: `${t.c.primary}1A`, alignItems: 'center', justifyContent: 'center' },
}));
