/**
 * `<Character persona state size/>` — the single public entry point (SPEC §6, §6b).
 *
 * Usage:
 *   <Character persona="sisu" state="idle" />                // home dock
 *   <Character persona={persona} state={chatState} size={220} locale="fi" />
 *
 * Kept here: unique SVG id prefix, localized accessibility label
 * ("Sisu, your trainer — thinking"), optional success haptic on `celebrate`,
 * and memoization so a parent re-render never re-renders the SVG tree.
 */
import * as Haptics from 'expo-haptics';
import { memo, useEffect, useId, useRef } from 'react';
import { Platform } from 'react-native';

import { HumanCharacter } from './HumanCharacter';
import { characterLabel } from './personas';
import type { CharacterProps } from './types';

export const DEFAULT_CHARACTER_SIZE = 120;

function CharacterImpl({
  persona,
  state,
  size = DEFAULT_CHARACTER_SIZE,
  locale = 'en',
  haptics = false,
  accessibilityLabel,
  style,
  testID,
}: CharacterProps) {
  // React ids contain characters (":", "«") that are invalid inside url(#…).
  const uid = `h${persona}${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const label = accessibilityLabel ?? characterLabel(persona, state, locale);

  const prev = useRef(state);
  useEffect(() => {
    if (haptics && state === 'celebrate' && prev.current !== 'celebrate' && Platform.OS !== 'web') {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => undefined);
    }
    prev.current = state;
  }, [state, haptics]);

  return (
    <HumanCharacter
      key={persona}
      persona={persona}
      state={state}
      size={size}
      uid={uid}
      label={label}
      style={style}
      testID={testID}
    />
  );
}

export const Character = memo(CharacterImpl);
Character.displayName = 'Character';
