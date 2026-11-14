/** Pill-shaped chip used for suggestions, filters and segmented choices. */
import type { StyleProp, ViewStyle } from 'react-native';

import { makeStyles, useTheme } from '@/theme';
import { Icon, type IconName } from './Icon';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

type Props = { label: string; onPress?: () => void; selected?: boolean; icon?: IconName; color?: string; style?: StyleProp<ViewStyle>; small?: boolean; testID?: string };

export function Chip({ label, onPress, selected, icon, color, style, small, testID }: Props) {
  const s = useStyles();
  const { c } = useTheme();
  const accent = color ?? c.primary;
  return (
    <PressableScale
      testID={testID}
      onPress={onPress}
      accessibilityState={{ selected: !!selected }}
      accessibilityLabel={label}
      style={[s.chip, small && s.small, selected && { backgroundColor: `${accent}26`, borderColor: `${accent}88` }, style]}
    >
      {icon ? <Icon name={icon} size={14} color={selected ? accent : c.textMuted} /> : null}
      <Text variant="caption" weight="600" color={selected ? accent : c.text} numberOfLines={2}>
        {label}
      </Text>
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 9,
    minHeight: 44,
    borderRadius: t.radius.pill,
    backgroundColor: t.c.surface,
    borderWidth: 1,
    borderColor: t.c.border,
    flexShrink: 1,
  },
  small: { paddingHorizontal: 14, paddingVertical: 6 },
}));
