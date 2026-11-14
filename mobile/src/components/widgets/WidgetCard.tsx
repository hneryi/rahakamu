/** Common frame for every inline widget: glass card, icon + title row, entrance animation. */
import type { ReactNode } from 'react';
import { View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';

import { GlassCard } from '@/components/ui/GlassCard';
import { Text } from '@/components/ui/Text';
import { makeStyles } from '@/theme';

type Props = { title?: string; emoji?: string; right?: ReactNode; children: ReactNode; tint?: string };

export function WidgetCard({ title, emoji, right, children, tint }: Props) {
  const s = useStyles();
  return (
    <Animated.View entering={FadeInDown.springify().damping(18)}>
      <GlassCard tint={tint} style={s.card}>
        {title || right ? (
          <View style={s.head}>
            {emoji ? <Text variant="body">{emoji}</Text> : null}
            <Text variant="callout" weight="700" style={s.title} numberOfLines={2}>
              {title}
            </Text>
            {right}
          </View>
        ) : null}
        {children}
      </GlassCard>
    </Animated.View>
  );
}

export function Pill({ label, color }: { label: string; color: string }) {
  return (
    <View style={{ paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, backgroundColor: `${color}22`, borderWidth: 1, borderColor: `${color}55` }}>
      <Text variant="micro" weight="800" color={color}>
        {label.toUpperCase()}
      </Text>
    </View>
  );
}

export function Stat({ label, value, color, big }: { label: string; value: string; color?: string; big?: boolean }) {
  return (
    <View style={{ flex: 1, minWidth: 90, gap: 2 }}>
      <Text variant="micro" tone="muted" numberOfLines={1}>
        {label.toUpperCase()}
      </Text>
      <Text variant={big ? 'title' : 'body'} weight="800" money color={color} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  card: { gap: 12 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { flex: 1 },
}));
