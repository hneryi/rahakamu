/**
 * Text-to-speech in the coach's voice (expo-speech; on web it drives
 * `speechSynthesis`).
 *
 * - The reply's language is detected from the text (the agent answers in the
 *   language of the question), falling back to the given locale.
 * - The best installed voice for that language is chosen
 *   (`getAvailableVoicesAsync`: enhanced / natural first; fi-FI, en-US/en-GB,
 *   sv-SE/sv-FI), with the persona's pitch and rate on top (SPEC §5.3).
 * - `speaking` is shared by every hook instance, so a stop anywhere (the mic,
 *   the stop pill, leaving the chat) updates every screen.
 */
import * as Speech from 'expo-speech';
import { useCallback, useEffect, useMemo, useSyncExternalStore } from 'react';
import { Platform } from 'react-native';

import type { Locale, PersonaId } from '@/api/types';
import { PERSONAS } from '@/characters';
import { toSpeech } from '@/components/chat/Markdown';
import { TTS_TAGS, detectLanguage, pickVoice } from '@/lib/speechLang';

// ── shared speaking state ──
let speakingNow = false;
const listeners = new Set<() => void>();
function setSpeaking(v: boolean) {
  if (speakingNow === v) return;
  speakingNow = v;
  listeners.forEach((l) => l());
}
const subscribe = (l: () => void) => {
  listeners.add(l);
  return () => listeners.delete(l);
};

let utteranceSeq = 0;

/** Stop any read-aloud (e.g. when the user starts a new recording). */
export function stopSpeaking(): void {
  utteranceSeq++;
  Speech.stop().catch(() => {});
  setSpeaking(false);
}

// ── voice list (cached once non-empty; browsers populate it lazily) ──
let voices: Speech.Voice[] | null = null;
async function loadVoices(): Promise<Speech.Voice[]> {
  if (voices) return voices;
  if (Platform.OS === 'web' && (typeof window === 'undefined' || !('speechSynthesis' in window))) return [];
  const timeout = new Promise<Speech.Voice[]>((r) => setTimeout(() => r([]), 1200));
  const list = await Promise.race([Speech.getAvailableVoicesAsync().catch(() => [] as Speech.Voice[]), timeout]);
  if (list.length) voices = list;
  return list;
}

/** Warm the voice list early so the first answer is not delayed. */
if (typeof window !== 'undefined' && (Platform.OS !== 'web' || 'speechSynthesis' in window)) loadVoices().catch(() => {});

export async function speakText(text: string, persona: PersonaId, fallback: Locale): Promise<Locale | null> {
  const clean = toSpeech(text);
  if (!clean || (Platform.OS === 'web' && (typeof window === 'undefined' || !('speechSynthesis' in window)))) return null;
  const lang = detectLanguage(clean, fallback);
  const { pitch, rate } = PERSONAS[persona].voice;
  const id = ++utteranceSeq;
  await Speech.stop().catch(() => {});
  const voice = pickVoice(await loadVoices(), lang);
  if (id !== utteranceSeq) return null; // a newer speak/stop happened meanwhile
  const done = () => {
    if (id === utteranceSeq) setSpeaking(false);
  };
  setSpeaking(true);
  Speech.speak(clean, {
    language: voice?.language ?? TTS_TAGS[lang][0],
    voice: voice?.identifier,
    pitch,
    rate,
    onDone: done,
    onStopped: done,
    onError: done,
  });
  return lang;
}

export function useSpeech() {
  const speaking = useSyncExternalStore(subscribe, () => speakingNow, () => false);

  const speak = useCallback((text: string, persona: PersonaId, fallback: Locale) => {
    speakText(text, persona, fallback).catch(() => setSpeaking(false));
  }, []);

  const stop = useCallback(() => stopSpeaking(), []);

  // Leaving the screen (back gesture included) ends the read-aloud.
  useEffect(() => stopSpeaking, []);

  return useMemo(() => ({ speaking, speak, stop }), [speaking, speak, stop]);
}
