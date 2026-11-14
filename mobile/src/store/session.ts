/**
 * Session store: who is using the app and how they like it.
 *
 * Holds the chosen demo customer, the coach persona (Sisu / Aava), UI language,
 * voice output and theme preference. Persisted to AsyncStorage so the onboarding
 * only happens once. `hydrated` lets the router wait for persisted state before
 * deciding whether to show onboarding (avoids a flash of the wrong screen).
 *
 * In a real S-mobiili integration `customerId` would come from the host app's
 * authenticated session instead of the demo picker; nothing else changes.
 */
import { getLocales } from 'expo-localization';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { Locale, PersonaId } from '@/api/types';
import { persistStorage } from './storage';

export type ThemePref = 'dark' | 'light' | 'system';

function deviceLocale(): Locale {
  try {
    const code = (getLocales()[0]?.languageCode ?? 'en').toLowerCase();
    return code === 'fi' ? 'fi' : code === 'sv' ? 'sv' : 'en';
  } catch {
    return 'en';
  }
}

type SessionState = {
  hydrated: boolean;
  onboarded: boolean;
  customerId: string | null;
  customerName: string | null;
  persona: PersonaId;
  locale: Locale;
  /** Speech-to-text language from the FI / EN / SV pill; null = follow the UI language. */
  voiceLang: Locale | null;
  /** Read answers aloud when the question was asked by voice. */
  voice: boolean;
  themePref: ThemePref;
  setCustomer: (id: string, name: string) => void;
  setPersona: (p: PersonaId) => void;
  setLocale: (l: Locale) => void;
  setVoiceLang: (l: Locale | null) => void;
  setVoice: (v: boolean) => void;
  setThemePref: (t: ThemePref) => void;
  completeOnboarding: () => void;
  resetOnboarding: () => void;
};

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      hydrated: false,
      onboarded: false,
      customerId: null,
      customerName: null,
      persona: 'sisu',
      locale: deviceLocale(),
      voiceLang: null,
      voice: true,
      themePref: 'dark',
      setCustomer: (customerId, customerName) => set({ customerId, customerName }),
      setPersona: (persona) => set({ persona }),
      // Changing the UI language resets the speech pill to follow it.
      setLocale: (locale) => set({ locale, voiceLang: null }),
      setVoiceLang: (voiceLang) => set({ voiceLang }),
      setVoice: (voice) => set({ voice }),
      setThemePref: (themePref) => set({ themePref }),
      completeOnboarding: () => set({ onboarded: true }),
      resetOnboarding: () => set({ onboarded: false }),
    }),
    {
      name: 'spankkibot.session.v1',
      storage: persistStorage,
      // v2: `voice` now means "answer spoken questions aloud" and defaults to on.
      version: 2,
      migrate: (persisted, version) => {
        const st = (persisted ?? {}) as Partial<SessionState>;
        return (version < 2 ? { ...st, voice: true, voiceLang: null } : st) as SessionState;
      },
      partialize: ({ hydrated: _h, ...rest }) => rest,
      onRehydrateStorage: () => () => {
        useSession.setState({ hydrated: true });
      },
    },
  ),
);
