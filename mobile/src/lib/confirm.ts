/** Cross-platform destructive-action confirmation (Alert on native, window.confirm on web). */
import { Alert, Platform } from 'react-native';

export function confirmAsync(title: string, okLabel: string, cancelLabel: string): Promise<boolean> {
  if (Platform.OS === 'web') {
    return Promise.resolve(typeof window !== 'undefined' && typeof window.confirm === 'function' ? window.confirm(title) : true);
  }
  return new Promise((resolve) => {
    Alert.alert(title, undefined, [
      { text: cancelLabel, style: 'cancel', onPress: () => resolve(false) },
      { text: okLabel, style: 'destructive', onPress: () => resolve(true) },
    ]);
  });
}
