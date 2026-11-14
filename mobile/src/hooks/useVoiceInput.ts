/**
 * Speech-to-text in Finnish, English or Swedish (SPEC §5.6).
 *
 * - Web: the browser's Web Speech API (`SpeechRecognition` /
 *   `webkitSpeechRecognition`; Chrome, Edge, Safari). Firefox has none.
 * - Native: `expo-speech-recognition` (needs a development build). It is loaded
 *   lazily inside try/catch, so in Expo Go `available` is false.
 *
 * Wherever recognition is missing or the microphone is refused, callers get an
 * `onError` code and fall back to the keyboard with a toast instead of crashing.
 *
 * Flow: start() (permission prompt on first use) → interim results update
 * `transcript` live → stop() (or the recogniser ends on silence) → `onFinal(text)`.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform } from 'react-native';

import type { Locale } from '@/api/types';
import { STT_TAG } from '@/lib/speechLang';

type SpeechModule = typeof import('expo-speech-recognition');
type Subscription = { remove: () => void };

// ── Web Speech API (typed locally: not in lib.dom for every TS target) ──
type WebResultList = ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
type WebRecognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: { results: WebResultList }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type WebRecognitionCtor = new () => WebRecognition;

function webCtor(): WebRecognitionCtor | null {
  if (Platform.OS !== 'web' || typeof window === 'undefined') return null;
  const w = window as unknown as { SpeechRecognition?: WebRecognitionCtor; webkitSpeechRecognition?: WebRecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

let cached: SpeechModule | null | undefined;
function loadModule(): SpeechModule | null {
  if (cached !== undefined) return cached;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    cached = require('expo-speech-recognition') as SpeechModule;
  } catch {
    cached = null;
  }
  return cached;
}

export function isVoiceAvailable(): boolean {
  if (Platform.OS === 'web') return webCtor() !== null;
  const m = loadModule();
  if (!m) return false;
  try {
    return m.ExpoSpeechRecognitionModule.isRecognitionAvailable();
  } catch {
    return false;
  }
}

export type VoiceError = 'unavailable' | 'denied' | 'no-speech' | 'error';

function mapError(code: string | undefined): VoiceError | null {
  switch (code) {
    case 'aborted':
      return null;
    case 'not-allowed':
    case 'service-not-allowed':
      return 'denied';
    case 'no-speech':
    case 'speech-timeout':
    case 'no-match':
      return 'no-speech';
    case 'audio-capture':
    case 'language-not-supported':
      return 'unavailable';
    default:
      return 'error';
  }
}

type Options = { lang: Locale; onFinal: (text: string, lang: Locale) => void; onError?: (e: VoiceError) => void };

export function useVoiceInput({ lang, onFinal, onError }: Options) {
  const [listening, setListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const subs = useRef<Subscription[]>([]);
  const web = useRef<WebRecognition | null>(null);
  const latest = useRef('');
  const wantStop = useRef(false);
  const active = useRef(false);
  const cbs = useRef({ onFinal, onError, lang });
  useEffect(() => {
    cbs.current = { onFinal, onError, lang };
  }, [onFinal, onError, lang]);

  const cleanup = useCallback(() => {
    subs.current.forEach((s) => s.remove());
    subs.current = [];
    if (web.current) {
      web.current.onresult = web.current.onerror = web.current.onend = null;
      web.current = null;
    }
    active.current = false;
    setListening(false);
  }, []);

  const finish = useCallback(() => {
    const text = latest.current.trim();
    const l = cbs.current.lang;
    cleanup();
    if (text) cbs.current.onFinal(text, l);
  }, [cleanup]);

  // Abort on unmount so the mic never stays open behind a closed screen.
  useEffect(
    () => () => {
      if (!active.current) return;
      try {
        web.current?.abort();
        if (!web.current) loadModule()?.ExpoSpeechRecognitionModule.abort();
      } catch {
        /* ignore */
      }
      subs.current.forEach((s) => s.remove());
    },
    [],
  );

  const startWeb = useCallback((Ctor: WebRecognitionCtor): boolean => {
    const rec = new Ctor();
    rec.lang = STT_TAG[cbs.current.lang];
    rec.interimResults = true;
    rec.continuous = false;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      let text = '';
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0]?.transcript ?? '';
      latest.current = text;
      setTranscript(text);
    };
    rec.onerror = (e) => {
      const err = mapError(e.error);
      if (err) {
        latest.current = err === 'no-speech' ? '' : latest.current;
        cbs.current.onError?.(err);
      }
      if (err === 'denied' || err === 'unavailable') cleanup();
    };
    rec.onend = finish;
    web.current = rec;
    try {
      rec.start();
    } catch {
      cleanup();
      cbs.current.onError?.('error');
      return false;
    }
    active.current = true;
    setListening(true);
    return true;
  }, [cleanup, finish]);

  const start = useCallback(async (): Promise<boolean> => {
    if (active.current) return true;
    wantStop.current = false;
    latest.current = '';
    setTranscript('');

    if (Platform.OS === 'web') {
      const Ctor = webCtor();
      if (!Ctor) {
        cbs.current.onError?.('unavailable');
        return false;
      }
      return startWeb(Ctor);
    }

    const m = loadModule();
    if (!m || !isVoiceAvailable()) {
      cbs.current.onError?.('unavailable');
      return false;
    }
    const mod = m.ExpoSpeechRecognitionModule;
    try {
      const perm = await mod.requestPermissionsAsync();
      if (!perm.granted) {
        cbs.current.onError?.('denied');
        return false;
      }
    } catch {
      cbs.current.onError?.('unavailable');
      return false;
    }
    subs.current.forEach((s) => s.remove());
    subs.current = [
      mod.addListener('result', (e) => {
        const text = e.results?.[0]?.transcript ?? '';
        latest.current = text;
        setTranscript(text);
      }),
      mod.addListener('error', (e) => {
        const err = mapError((e as { error?: string }).error);
        if (err) cbs.current.onError?.(err);
        if (err === 'no-speech') latest.current = '';
        cleanup();
      }),
      mod.addListener('end', finish),
    ];
    try {
      mod.start({ lang: STT_TAG[cbs.current.lang], interimResults: true, continuous: false, maxAlternatives: 1 });
      active.current = true;
      setListening(true);
      // User already released the button while the permission prompt was open.
      if (wantStop.current) mod.stop();
      return true;
    } catch {
      cleanup();
      cbs.current.onError?.('error');
      return false;
    }
  }, [cleanup, finish, startWeb]);

  /** Stop listening and deliver what was heard. */
  const stop = useCallback(() => {
    wantStop.current = true;
    if (!active.current) return;
    try {
      if (web.current) web.current.stop();
      else loadModule()?.ExpoSpeechRecognitionModule.stop();
    } catch {
      finish();
    }
  }, [finish]);

  return { listening, transcript, start, stop, isActive: () => active.current };
}
