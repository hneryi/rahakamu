/**
 * Themed text with the spec's type scale (34/22/17/15/13/12). `money` switches on
 * tabular numerals so amounts align and do not jitter while animating.
 */
import { Text as RNText, type TextProps, type TextStyle } from 'react-native';

import { fontFamily, tabular, useTheme, type Palette } from '@/theme';

type Variant = 'hero' | 'title' | 'body' | 'callout' | 'caption' | 'micro';
type Tone = 'text' | 'muted' | 'faint' | 'primary' | 'accent' | 'warn' | 'amber' | 'good' | 'onPrimary';

export type AppTextProps = TextProps & {
  variant?: Variant;
  tone?: Tone;
  weight?: '400' | '500' | '600' | '700' | '800';
  money?: boolean;
  align?: TextStyle['textAlign'];
  color?: string;
};

const sizes: Record<Variant, { fontSize: number; lineHeight: number; weight: TextStyle['fontWeight']; letterSpacing?: number }> = {
  hero: { fontSize: 34, lineHeight: 40, weight: '700', letterSpacing: -0.6 },
  title: { fontSize: 22, lineHeight: 28, weight: '700', letterSpacing: -0.3 },
  body: { fontSize: 17, lineHeight: 24, weight: '400' },
  callout: { fontSize: 15, lineHeight: 21, weight: '400' },
  caption: { fontSize: 13, lineHeight: 18, weight: '500' },
  micro: { fontSize: 12, lineHeight: 16, weight: '600', letterSpacing: 0.2 },
};

function toneColor(c: Palette, tone: Tone): string {
  switch (tone) {
    case 'muted': return c.textMuted;
    case 'faint': return c.textFaint;
    case 'primary': return c.primary;
    case 'accent': return c.accent;
    case 'warn': return c.warn;
    case 'amber': return c.amber;
    case 'good': return c.good;
    case 'onPrimary': return c.primaryText;
    default: return c.text;
  }
}

export function Text({ variant = 'body', tone = 'text', weight, money, align, color, style, ...rest }: AppTextProps) {
  const { c } = useTheme();
  const v = sizes[variant];
  return (
    <RNText
      {...rest}
      style={[
        { fontFamily, fontSize: v.fontSize, lineHeight: v.lineHeight, fontWeight: weight ?? v.weight, letterSpacing: v.letterSpacing, color: color ?? toneColor(c, tone), textAlign: align },
        money && tabular,
        style,
      ]}
    />
  );
}
