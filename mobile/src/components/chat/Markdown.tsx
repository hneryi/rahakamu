/**
 * "Markdown-lite" renderer for AI answers (SPEC §4.2 tokens).
 *
 * The agent is prompted to use only **bold**, *italic*, bullet/numbered lists,
 * short headings and an optional closing "💡 concept" line. Supporting just that
 * subset keeps rendering predictable while tokens stream in (half-finished
 * markup simply shows as text until it closes) and avoids a heavy dependency.
 * The 💡 line is rendered as a highlighted "Concept" tip — the pedagogical hook
 * that ends many answers.
 */
import { Fragment } from 'react';
import { View } from 'react-native';

import { Text } from '@/components/ui/Text';
import { makeStyles, useTheme } from '@/theme';

type Props = { text: string; color?: string; size?: 'body' | 'callout' };

function Inline({ text, size, color }: { text: string; size: 'body' | 'callout'; color?: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)/g).filter(Boolean);
  return (
    <Text variant={size} color={color}>
      {parts.map((p, i) => {
        if (p.startsWith('**') && p.endsWith('**') && p.length > 4)
          return (
            <Text key={i} variant={size} weight="700" color={color}>
              {p.slice(2, -2)}
            </Text>
          );
        if (p.startsWith('*') && p.endsWith('*') && p.length > 2)
          return (
            <Text key={i} variant={size} color={color} style={{ fontStyle: 'italic' }}>
              {p.slice(1, -1)}
            </Text>
          );
        return <Fragment key={i}>{p}</Fragment>;
      })}
    </Text>
  );
}

export function Markdown({ text, color, size = 'body' }: Props) {
  const s = useStyles();
  const { c } = useTheme();
  const lines = text.replace(/\r/g, '').split('\n');
  const blocks: React.ReactNode[] = [];
  lines.forEach((raw, i) => {
    const line = raw.trimEnd();
    if (!line.trim()) {
      blocks.push(<View key={`sp${i}`} style={s.spacer} />);
      return;
    }
    const bullet = /^\s*(?:[-*•])\s+(.*)$/.exec(line);
    const numbered = /^\s*(\d+)[.)]\s+(.*)$/.exec(line);
    const heading = /^#{1,4}\s+(.*)$/.exec(line);
    if (line.trim().startsWith('💡')) {
      blocks.push(
        <View key={i} style={s.tip}>
          <Text variant="callout">💡</Text>
          <View style={{ flex: 1 }}>
            <Inline text={line.trim().replace(/^💡\s*/, '')} size="callout" color={color} />
          </View>
        </View>,
      );
    } else if (heading) {
      blocks.push(
        <Text key={i} variant={size} weight="800" color={color}>
          {heading[1].replace(/\*\*/g, '')}
        </Text>,
      );
    } else if (bullet || numbered) {
      blocks.push(
        <View key={i} style={s.li}>
          <Text variant={size} color={c.accent} weight="700" style={s.marker}>
            {numbered ? `${numbered[1]}.` : '•'}
          </Text>
          <View style={{ flex: 1 }}>
            <Inline text={(bullet ? bullet[1] : numbered![2]) ?? ''} size={size} color={color} />
          </View>
        </View>,
      );
    } else {
      blocks.push(<Inline key={i} text={line} size={size} color={color} />);
    }
  });
  return <View style={s.wrap}>{blocks}</View>;
}

/** Strip markup + emoji for text-to-speech. */
export function toSpeech(text: string): string {
  return text
    .replace(/\*\*|__|\*|#+\s/g, '')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu, '')
    .replace(/^\s*[-•]\s+/gm, '')
    .replace(/\s+/g, ' ')
    .trim();
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: 4 },
  spacer: { height: 4 },
  li: { flexDirection: 'row', gap: 8, paddingLeft: 2 },
  marker: { minWidth: 14 },
  tip: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 6,
    padding: 12,
    borderRadius: 16,
    backgroundColor: `${t.c.accent}14`,
    borderWidth: 1,
    borderColor: `${t.c.accent}33`,
  },
}));
