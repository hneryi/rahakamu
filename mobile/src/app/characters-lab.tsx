/**
 * /characters-lab — showcase for the two AI coaches (SPEC §6 / §6b).
 *
 * Shows Sisu the Trainer and Aava the Mentor in every state at the sizes the
 * app uses (64 avatar, 120 home dock, 240 chat hero) on the dark brand
 * background, with state buttons, auto-cycle and the chat-stream sequence
 * (listening → thinking → talking → mood) to check the blends.
 * Depends only on `@/characters` and React Native primitives.
 */
import { useEffect, useRef, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import {
  CHARACTER_STATES,
  Character,
  PERSONA_LIST,
  PERSONAS,
  characterLabel,
  type CharacterLocale,
  type CharacterState,
  type PersonaId,
} from '@/characters';

const SIZES = [64, 120, 240] as const;
const BG = '#07140F';
const SURFACE = 'rgba(255,255,255,0.06)';
const BORDER = 'rgba(255,255,255,0.08)';
const TEXT = '#F2F7F4';
const MUTED = '#9FB3A9';
const PRIMARY = '#00B26F';

const CHAT_SCRIPT: readonly [CharacterState, number][] = [
  ['listening', 1800],
  ['thinking', 2200],
  ['talking', 3600],
  ['happy', 2200],
  ['talking', 2000],
  ['celebrate', 3200],
  ['concerned', 2600],
  ['idle', 0],
];

function Chip({
  label,
  active,
  onPress,
  color = PRIMARY,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  color?: string;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={({ pressed }) => [
        styles.chip,
        active && { backgroundColor: color, borderColor: color },
        pressed && { opacity: 0.75 },
      ]}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

export default function CharactersLab() {
  const [state, setState] = useState<CharacterState>('idle');
  const [size, setSize] = useState<number>(240);
  const [gridSize, setGridSize] = useState<number | 'all'>(120);
  const [locale, setLocale] = useState<CharacterLocale>('en');
  const [cycle, setCycle] = useState(false);
  const [scriptRunning, setScriptRunning] = useState(false);
  const [showGrid, setShowGrid] = useState(true);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    if (!cycle) return undefined;
    const id = setInterval(() => {
      setState((s) => CHARACTER_STATES[(CHARACTER_STATES.indexOf(s) + 1) % CHARACTER_STATES.length]);
    }, 2600);
    return () => clearInterval(id);
  }, [cycle]);

  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const runChatScript = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setCycle(false);
    setScriptRunning(true);
    let at = 0;
    CHAT_SCRIPT.forEach(([s, ms], i) => {
      timers.current.push(
        setTimeout(() => {
          setState(s);
          if (i === CHAT_SCRIPT.length - 1) setScriptRunning(false);
        }, at),
      );
      at += ms;
    });
  };

  const personas: PersonaId[] = ['sisu', 'aava'];

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={styles.h1}>Characters Lab</Text>
      <Text style={styles.sub}>
        Sisu the Trainer and Aava the Mentor: layered vector art, one shared clock, smooth blends between states.
      </Text>

      <View style={styles.stage}>
        {personas.map((p) => (
          <View key={p} style={styles.stageItem}>
            <Character persona={p} state={state} size={size} locale={locale} haptics />
            <Text style={[styles.name, { color: PERSONAS[p].color }]}>
              {PERSONAS[p].name} · {PERSONAS[p].title[locale]}
            </Text>
            <Text style={styles.caption}>{characterLabel(p, state, locale)}</Text>
          </View>
        ))}
      </View>

      <Text style={styles.label}>State</Text>
      <View style={styles.row}>
        {CHARACTER_STATES.map((s) => (
          <Chip
            key={s}
            label={s}
            active={state === s}
            onPress={() => {
              setCycle(false);
              setState(s);
            }}
          />
        ))}
      </View>

      <Text style={styles.label}>Size (px)</Text>
      <View style={styles.row}>
        {SIZES.map((s) => (
          <Chip key={s} label={String(s)} active={size === s} onPress={() => setSize(s)} />
        ))}
        <View style={styles.spacer} />
        <Chip label="EN" active={locale === 'en'} onPress={() => setLocale('en')} />
        <Chip label="FI" active={locale === 'fi'} onPress={() => setLocale('fi')} />
        <Chip label="SV" active={locale === 'sv'} onPress={() => setLocale('sv')} />
      </View>

      <Text style={styles.label}>Playback</Text>
      <View style={styles.row}>
        <Chip label={cycle ? 'auto-cycle: on' : 'auto-cycle: off'} active={cycle} onPress={() => setCycle((c) => !c)} />
        <Chip
          label={scriptRunning ? 'chat flow running…' : '▶ simulate chat flow'}
          active={scriptRunning}
          onPress={runChatScript}
        />
      </View>

      <Text style={styles.h2}>All states</Text>
      <View style={styles.row}>
        {SIZES.map((s) => (
          <Chip key={s} label={`${s}px`} active={showGrid && gridSize === s} onPress={() => { setGridSize(s); setShowGrid(true); }} />
        ))}
        <Chip label="all sizes" active={showGrid && gridSize === 'all'} onPress={() => { setGridSize('all'); setShowGrid(true); }} />
        <Chip label="hide" active={!showGrid} onPress={() => setShowGrid(false)} />
      </View>
      {showGrid
        ? personas.map((p) => (
            <View key={p} style={styles.gridBlock}>
              <Text style={[styles.name, { color: PERSONAS[p].color }]}>{PERSONAS[p].name}</Text>
              {(gridSize === 'all' ? SIZES : [gridSize]).map((gs) => (
                <View key={gs} style={styles.grid} testID={`grid-${p}-${gs}`}>
                  {CHARACTER_STATES.map((s) => (
                    <View key={s} style={[styles.cell, { width: gs + 16 }]}>
                      <Character persona={p} state={s} size={gs} locale={locale} />
                      <Text style={styles.cellText}>{s}</Text>
                    </View>
                  ))}
                </View>
              ))}
            </View>
          ))
        : null}

      <Text style={styles.h2}>Persona meta</Text>
      {PERSONA_LIST.map((p) => (
        <View key={p.id} style={styles.card}>
          <View style={styles.cardHead}>
            <Character persona={p.id} state="idle" size={64} locale={locale} />
            <View style={styles.cardText}>
              <Text style={[styles.name, { color: p.color }]}>
                {p.emoji} {p.name} — {p.title[locale]}
              </Text>
              <Text style={styles.caption}>{p.tagline[locale]}</Text>
            </View>
          </View>
          <View style={styles.row}>
            <View style={[styles.swatch, { backgroundColor: p.color }]} />
            <View style={[styles.swatch, { backgroundColor: p.accent }]} />
            <Text style={styles.mono}>
              {p.color} / {p.accent} · voice pitch {p.voice.pitch} rate {p.voice.rate}
            </Text>
          </View>
        </View>
      ))}
      <View style={{ height: 48 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: BG },
  content: { padding: 16, paddingTop: 56, maxWidth: 760, width: '100%', alignSelf: 'center' },
  h1: { color: TEXT, fontSize: 32, fontWeight: '800', letterSpacing: -0.5 },
  h2: { color: TEXT, fontSize: 22, fontWeight: '700', marginTop: 28, marginBottom: 8 },
  sub: { color: MUTED, fontSize: 15, marginTop: 6, lineHeight: 21 },
  stage: {
    marginTop: 20,
    paddingVertical: 24,
    paddingHorizontal: 8,
    borderRadius: 24,
    backgroundColor: SURFACE,
    borderWidth: 1,
    borderColor: BORDER,
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-around',
    alignItems: 'flex-end',
    gap: 16,
  },
  stageItem: { alignItems: 'center', gap: 6 },
  name: { fontSize: 17, fontWeight: '700' },
  caption: { color: MUTED, fontSize: 13 },
  label: {
    color: MUTED,
    fontSize: 13,
    fontWeight: '600',
    marginTop: 18,
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.8,
  },
  row: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  spacer: { width: 12 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: SURFACE,
  },
  chipText: { color: TEXT, fontSize: 14, fontWeight: '600' },
  chipTextActive: { color: '#03130C' },
  gridBlock: { marginTop: 12 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 8 },
  cell: {
    alignItems: 'center',
    paddingVertical: 10,
    borderRadius: 18,
    backgroundColor: SURFACE,
    borderWidth: 1,
    borderColor: BORDER,
  },
  cellText: { color: MUTED, fontSize: 12, marginTop: 4 },
  card: {
    marginTop: 10,
    padding: 16,
    borderRadius: 24,
    backgroundColor: SURFACE,
    borderWidth: 1,
    borderColor: BORDER,
    gap: 12,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  cardText: { flex: 1, gap: 4 },
  swatch: { width: 22, height: 22, borderRadius: 11, borderWidth: 1, borderColor: BORDER },
  mono: { color: MUTED, fontSize: 12, fontFamily: 'monospace' },
});
