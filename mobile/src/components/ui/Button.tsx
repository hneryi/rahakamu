/**
 * Primary / secondary / ghost buttons with haptics and a loading state.
 * Primary uses the S-green; `color` lets persona-specific CTAs use Sisu amber or
 * Aava mint without new variants.
 */
import { ActivityIndicator, View, type StyleProp, type ViewStyle } from 'react-native';

import { makeStyles, useTheme } from '@/theme';
import { Icon, type IconName } from './Icon';
import { PressableScale } from './PressableScale';
import { Text } from './Text';

type Props = {
  label: string;
  onPress?: () => void;
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger';
  icon?: IconName;
  loading?: boolean;
  disabled?: boolean;
  color?: string;
  size?: 'md' | 'sm';
  style?: StyleProp<ViewStyle>;
  full?: boolean;
  testID?: string;
};

export function Button({ label, onPress, variant = 'primary', icon, loading, disabled, color, size = 'md', style, full, testID }: Props) {
  const s = useStyles();
  const { c } = useTheme();
  const bg = variant === 'primary' ? (color ?? c.primary) : variant === 'secondary' ? c.surfaceStrong : variant === 'danger' ? `${c.warn}22` : 'transparent';
  const fg = variant === 'primary' ? c.primaryText : variant === 'danger' ? c.warn : (color ?? c.text);
  return (
    <PressableScale
      testID={testID}
      onPress={disabled || loading ? undefined : onPress}
      accessibilityLabel={label}
      accessibilityState={{ disabled: !!disabled, busy: !!loading }}
      style={[s.base, size === 'sm' && s.sm, { backgroundColor: bg, opacity: disabled ? 0.45 : 1 }, variant === 'secondary' && s.bordered, full && s.full, style]}
    >
      <View style={s.row}>
        {loading ? <ActivityIndicator color={fg} size="small" /> : icon ? <Icon name={icon} size={size === 'sm' ? 16 : 19} color={fg} /> : null}
        <Text variant={size === 'sm' ? 'caption' : 'callout'} weight="700" color={fg} numberOfLines={1}>
          {label}
        </Text>
      </View>
    </PressableScale>
  );
}

const useStyles = makeStyles((t) => ({
  base: { minHeight: 50, paddingHorizontal: 20, borderRadius: t.radius.pill, alignItems: 'center', justifyContent: 'center' },
  sm: { minHeight: 36, paddingHorizontal: 14 },
  bordered: { borderWidth: 1, borderColor: t.c.border },
  full: { alignSelf: 'stretch' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
}));
