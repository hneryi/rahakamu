/**
 * Tab group with the custom floating glass tab bar: Home · Insights · Goals · Learn.
 *
 * Also the onboarding gate: until persisted session state is hydrated we render
 * nothing (splash stays up); if the user has not picked a customer + coach yet,
 * we redirect to onboarding.
 */
import { Redirect } from 'expo-router';
import { TabList, TabSlot, TabTrigger, Tabs } from 'expo-router/ui';
import { View } from 'react-native';

import { GlassTabBar, TabButton } from '@/components/GlassTabBar';
import { useT } from '@/i18n';
import { useSession } from '@/store/session';
import { useTheme } from '@/theme';

export default function TabsLayout() {
  const { t } = useT();
  const { c } = useTheme();
  const hydrated = useSession((s) => s.hydrated);
  const onboarded = useSession((s) => s.onboarded && !!s.customerId);

  if (!hydrated) return <View style={{ flex: 1, backgroundColor: c.bgSolid }} />;
  if (!onboarded) return <Redirect href="/onboarding" />;

  return (
    <Tabs>
      <TabSlot style={{ flex: 1 }} />
      <TabList asChild>
        <GlassTabBar>
          <TabTrigger name="index" href="/" asChild>
            <TabButton tid="tab-home" icon="home" label={t('tabs.home')} />
          </TabTrigger>
          <TabTrigger name="insights" href="/insights" asChild>
            <TabButton tid="tab-insights" icon="chart" label={t('tabs.insights')} />
          </TabTrigger>
          <TabTrigger name="goals" href="/goals" asChild>
            <TabButton tid="tab-goals" icon="target" label={t('tabs.goals')} />
          </TabTrigger>
          <TabTrigger name="learn" href="/learn" asChild>
            <TabButton tid="tab-learn" icon="book" label={t('tabs.learn')} />
          </TabTrigger>
        </GlassTabBar>
      </TabList>
    </Tabs>
  );
}
