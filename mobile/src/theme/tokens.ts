/**
 * Design tokens for SPankkiBot (SPEC §5.4).
 *
 * Why tokens instead of ad-hoc colours: the app is meant to be lifted into
 * S-mobiili, whose design team will want to re-skin it. Every colour, radius,
 * spacing step and type size used by components lives here, so a re-brand (or the
 * host app's light mode) is a one-file change.
 *
 * Dark is the primary, "premium glass" theme. Light is a faithful inversion that
 * keeps the same semantic names, so components never branch on the theme.
 */
import { Platform, type TextStyle } from 'react-native';

export type ThemeName = 'dark' | 'light';

export type Palette = {
  /** Background gradient stops (top → bottom). */
  bg: readonly [string, string];
  /** Solid fallback for places a gradient cannot go (status bar, web body). */
  bgSolid: string;
  /** Glass surface fill and its 1 px hairline border. */
  surface: string;
  surfaceStrong: string;
  border: string;
  /** Tab bar / sheet backdrop when blur is unavailable. */
  glassFallback: string;
  text: string;
  textMuted: string;
  textFaint: string;
  primary: string;
  primaryText: string;
  accent: string;
  amber: string;
  warn: string;
  good: string;
  overlay: string;
  basket: { fixed: string; irregular: string; leak: string; income: string; saving: string };
  chartGrid: string;
  shadow: string;
};

const dark: Palette = {
  bg: ['#07140F', '#0B1F17'],
  bgSolid: '#07140F',
  surface: 'rgba(255,255,255,0.06)',
  surfaceStrong: 'rgba(255,255,255,0.10)',
  border: 'rgba(255,255,255,0.08)',
  glassFallback: 'rgba(12,30,22,0.92)',
  text: '#F2F7F4',
  textMuted: '#9FB3A9',
  textFaint: '#6B8278',
  primary: '#00B26F',
  primaryText: '#03130C',
  accent: '#3DD9B4',
  amber: '#F5A524',
  warn: '#FF6B5A',
  good: '#3DD9B4',
  overlay: 'rgba(2,8,6,0.66)',
  basket: {
    fixed: '#5B8DEF',
    irregular: '#F5A524',
    leak: '#FF6B8A',
    income: '#3DD9B4',
    saving: '#00B26F',
  },
  chartGrid: 'rgba(255,255,255,0.07)',
  shadow: '#000000',
};

const light: Palette = {
  bg: ['#F4FAF6', '#E6F2EB'],
  bgSolid: '#F4FAF6',
  surface: 'rgba(255,255,255,0.78)',
  surfaceStrong: '#FFFFFF',
  border: 'rgba(7,20,15,0.08)',
  glassFallback: 'rgba(255,255,255,0.94)',
  text: '#0B1F17',
  textMuted: '#4D6359',
  textFaint: '#7C9187',
  primary: '#00975E',
  primaryText: '#FFFFFF',
  accent: '#12A887',
  amber: '#C77F00',
  warn: '#E04A3A',
  good: '#12A887',
  overlay: 'rgba(7,20,15,0.35)',
  basket: {
    fixed: '#3F6FD8',
    irregular: '#D88A00',
    leak: '#E0456A',
    income: '#12A887',
    saving: '#00975E',
  },
  chartGrid: 'rgba(7,20,15,0.07)',
  shadow: '#0B1F17',
};

export const palettes: Record<ThemeName, Palette> = { dark, light };

/** 4-pt spacing scale; 16 and 24 are the "generous" defaults from the spec. */
export const space = { xxs: 4, xs: 8, sm: 12, md: 16, lg: 24, xl: 32, xxl: 48 } as const;

export const radius = { sm: 12, md: 18, lg: 24, pill: 999 } as const;

/** Type scale 34/22/17/15/13 (+11 for chart ticks). */
export const fontSize = { hero: 34, title: 22, body: 17, callout: 15, caption: 13, micro: 12 } as const;

/** Money is always tabular so digits do not jiggle while values animate. */
export const tabular: TextStyle = { fontVariant: ['tabular-nums'] };

export const fontFamily = Platform.select({
  web: 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, system-ui, sans-serif',
  default: undefined,
});

/** Layout constants shared by the tab bar, dock and scroll insets. */
export const layout = {
  maxWidth: 480,
  tabBarHeight: 64,
  tabBarGap: 12,
  dockHeight: 168,
  gutter: 16,
} as const;

/** Spring presets so every animated element moves with the same "feel". */
export const springs = {
  snappy: { damping: 18, stiffness: 220, mass: 0.8 },
  gentle: { damping: 16, stiffness: 120, mass: 1 },
  bouncy: { damping: 10, stiffness: 180, mass: 0.9 },
} as const;

export type Theme = {
  name: ThemeName;
  c: Palette;
  space: typeof space;
  radius: typeof radius;
  font: typeof fontSize;
};

export function buildTheme(name: ThemeName): Theme {
  return { name, c: palettes[name], space, radius, font: fontSize };
}

/** Persona accent colours (mirrors characters/PERSONAS; kept here so theme never imports UI). */
export const personaColor = { sisu: '#F5A524', aava: '#3DD9B4' } as const;
