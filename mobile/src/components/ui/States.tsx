/** Shared empty / error states so every screen fails gracefully and consistently. */
import { View } from 'react-native';

import { useT } from '@/i18n';
import { Button } from './Button';
import { Text } from './Text';

export function ErrorState({ onRetry, message }: { onRetry?: () => void; message?: string }) {
  const { t } = useT();
  return (
    <View style={{ alignItems: 'center', gap: 12, paddingVertical: 24 }}>
      <Text variant="hero">😕</Text>
      <Text variant="callout" tone="muted" align="center">
        {message ?? t('common.error')}
      </Text>
      {onRetry ? <Button label={t('common.retry')} icon="refresh" variant="secondary" size="sm" onPress={onRetry} /> : null}
    </View>
  );
}

export function EmptyState({ emoji = '🌱', text }: { emoji?: string; text: string }) {
  return (
    <View style={{ alignItems: 'center', gap: 8, paddingVertical: 24 }}>
      <Text variant="hero">{emoji}</Text>
      <Text variant="callout" tone="muted" align="center">
        {text}
      </Text>
    </View>
  );
}
