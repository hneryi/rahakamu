/**
 * Pressable that springs down to 97 % while pressed — the subtle physical
 * response that makes cards and buttons feel native rather than web-like.
 */
import type { ReactNode } from 'react';
import { Pressable, type PressableProps, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

import { haptic } from '@/lib/haptics';
import { springs } from '@/theme';

const APressable = Animated.createAnimatedComponent(Pressable);

type Props = Omit<PressableProps, 'style' | 'children'> & {
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
  scaleTo?: number;
  hapticOnPress?: boolean;
};

export function PressableScale({ style, children, scaleTo = 0.97, hapticOnPress = true, onPressIn, onPressOut, onPress, ...rest }: Props) {
  const scale = useSharedValue(1);
  const aStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.get() }] }));
  return (
    <APressable
      accessibilityRole="button"
      {...rest}
      onPressIn={(e) => {
        scale.set(withSpring(scaleTo, springs.snappy));
        onPressIn?.(e);
      }}
      onPressOut={(e) => {
        scale.set(withSpring(1, springs.snappy));
        onPressOut?.(e);
      }}
      onPress={(e) => {
        if (hapticOnPress) haptic.tap();
        onPress?.(e);
      }}
      style={[style, aStyle]}
    >
      {children}
    </APressable>
  );
}
