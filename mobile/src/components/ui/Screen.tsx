/**
 * Standard tab screen scaffold: background, safe-area aware scroll view, large
 * title header with optional right accessory, and bottom padding that clears the
 * floating tab bar (and the character dock on Home).
 */
import type { ReactNode } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { layout, makeStyles, useTheme } from '@/theme';
import { Background } from './Background';
import { Text } from './Text';

type Props = {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  header?: ReactNode;
  children: ReactNode;
  bottomExtra?: number;
  onRefresh?: () => void;
  refreshing?: boolean;
  testID?: string;
};

export function Screen({ title, subtitle, right, header, children, bottomExtra = 0, onRefresh, refreshing = false, testID }: Props) {
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const { c } = useTheme();
  return (
    <View style={s.root} testID={testID}>
      <Background />
      <ScrollView
        contentContainerStyle={[s.content, { paddingTop: insets.top + 12, paddingBottom: insets.bottom + layout.tabBarHeight + layout.tabBarGap + 28 + bottomExtra }]}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        refreshControl={onRefresh ? <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={c.primary} colors={[c.primary]} /> : undefined}
      >
        {header}
        {title ? (
          <View style={s.header}>
            <View style={s.titles}>
              <Text variant="hero" accessibilityRole="header">
                {title}
              </Text>
              {subtitle ? (
                <Text variant="callout" tone="muted">
                  {subtitle}
                </Text>
              ) : null}
            </View>
            {right}
          </View>
        ) : null}
        {children}
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  root: { flex: 1, backgroundColor: t.c.bgSolid, overflow: 'hidden' },
  content: { paddingHorizontal: layout.gutter, gap: t.space.md, width: '100%', maxWidth: layout.maxWidth, alignSelf: 'center' },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, marginBottom: 4 },
  titles: { flex: 1, gap: 2 },
}));
