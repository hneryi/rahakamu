/**
 * Money Gym progress: completed lessons, quiz scores and the daily streak.
 *
 * Kept on-device (AsyncStorage) on purpose: learning progress is personal, needs
 * no server round-trip and survives offline use. A streak counts consecutive
 * calendar days with at least one completed lesson — the habit loop that makes
 * micro-learning stick.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { persistStorage } from './storage';

function dayKey(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function daysBetween(a: string, b: string): number {
  const pa = Date.parse(`${a}T00:00:00`);
  const pb = Date.parse(`${b}T00:00:00`);
  return Math.round((pb - pa) / 86_400_000);
}

type LearnState = {
  completed: Record<string, { score: number; at: string }>;
  streak: number;
  lastDay: string | null;
  completeLesson: (id: string, score: number) => { streak: number; isNewDay: boolean };
  /** Streak shown to the user: 0 if the chain was broken (missed a day). */
  currentStreak: () => number;
  reset: () => void;
};

export const useLearn = create<LearnState>()(
  persist(
    (set, get) => ({
      completed: {},
      streak: 0,
      lastDay: null,
      completeLesson: (id, score) => {
        const today = dayKey();
        const { lastDay, streak, completed } = get();
        let next = streak;
        let isNewDay = false;
        if (lastDay !== today) {
          isNewDay = true;
          next = lastDay && daysBetween(lastDay, today) === 1 ? streak + 1 : 1;
        }
        const prev = completed[id];
        set({
          completed: { ...completed, [id]: { score: Math.max(score, prev?.score ?? 0), at: today } },
          streak: next,
          lastDay: today,
        });
        return { streak: next, isNewDay };
      },
      currentStreak: () => {
        const { lastDay, streak } = get();
        if (!lastDay) return 0;
        return daysBetween(lastDay, dayKey()) <= 1 ? streak : 0;
      },
      reset: () => set({ completed: {}, streak: 0, lastDay: null }),
    }),
    { name: 'spankkibot.learn.v1', storage: persistStorage },
  ),
);
