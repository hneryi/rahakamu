/**
 * Theme access for components.
 *
 * `useTheme()` resolves the user's preference (dark / light / system) into a
 * concrete token set. `makeStyles(factory)` builds a memoised hook so components
 * write `const s = useStyles()` and get StyleSheet objects that update when the
 * theme flips — without every component re-implementing that plumbing.
 */
import { useMemo } from 'react';
import { StyleSheet, useColorScheme, type ImageStyle, type TextStyle, type ViewStyle } from 'react-native';

import { useSession } from '@/store/session';
import { buildTheme, type Theme, type ThemeName } from './tokens';

export * from './tokens';

const themes: Record<ThemeName, Theme> = { dark: buildTheme('dark'), light: buildTheme('light') };

export function useTheme(): Theme {
  const pref = useSession((s) => s.themePref);
  const system = useColorScheme();
  const name: ThemeName = pref === 'system' ? (system === 'light' ? 'light' : 'dark') : pref;
  return themes[name];
}

/** Classic named-styles map (RN 0.88 no longer exports `StyleSheet.NamedStyles`). */
type NamedStyles<T> = { [P in keyof T]: ViewStyle | TextStyle | ImageStyle };

export function makeStyles<T extends NamedStyles<T> | NamedStyles<any>>(factory: (t: Theme) => T & NamedStyles<any>) {
  const cache = new Map<ThemeName, T>();
  return function useStyles(): T {
    const theme = useTheme();
    return useMemo(() => {
      const hit = cache.get(theme.name);
      if (hit) return hit;
      const created = StyleSheet.create(factory(theme)) as T;
      cache.set(theme.name, created);
      return created;
    }, [theme]);
  };
}
