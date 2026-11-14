/**
 * Small "Demo data" badge, visible whenever any response came from fixtures —
 * judges and testers always know whether they are looking at live data.
 */
import { useT } from '@/i18n';
import { useUi } from '@/store/ui';
import { makeStyles, useTheme } from '@/theme';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

export function DemoBadge() {
  const demo = useUi((s) => s.demoData);
  const showToast = useUi((s) => s.showToast);
  const { t } = useT();
  const s = useStyles();
  const { c } = useTheme();
  if (!demo) return null;
  return (
    <PressableScale testID="demo-badge" hitSlop={10} onPress={() => showToast(t('common.demoDataHint'), 'info')} style={s.badge} accessibilityLabel={t('common.demoDataHint')}>
      <Text variant="micro" weight="700" color={c.amber}>
        ● {t('common.demoData')}
      </Text>
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  badge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: t.radius.pill, backgroundColor: `${t.c.amber}1F`, borderWidth: 1, borderColor: `${t.c.amber}55` },
}));
