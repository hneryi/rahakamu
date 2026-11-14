/**
 * Transient UI state shared across screens: toasts, the "demo data" flag and the
 * hand-off payload from Home → Chat (a prefilled question or a picked image).
 *
 * Passing an image through router params would mean serialising megabytes of
 * base64 into a URL, so the Home dock stores it here and Chat picks it up.
 */
import { create } from 'zustand';

export type Toast = { id: number; text: string; tone: 'info' | 'good' | 'warn' };

export type PendingAttachment = { uri: string; base64: string };

type UiState = {
  toasts: Toast[];
  /** True once any request was served from local fixtures (mock mode or API unreachable). */
  demoData: boolean;
  pendingAttachment: PendingAttachment | null;
  showToast: (text: string, tone?: Toast['tone']) => void;
  dismissToast: (id: number) => void;
  setDemoData: (v: boolean) => void;
  setPendingAttachment: (a: PendingAttachment | null) => void;
};

let seq = 0;

export const useUi = create<UiState>()((set, get) => ({
  toasts: [],
  demoData: false,
  pendingAttachment: null,
  showToast: (text, tone = 'info') => {
    const id = ++seq;
    set({ toasts: [...get().toasts.slice(-2), { id, text, tone }] });
    setTimeout(() => get().dismissToast(id), 3200);
  },
  dismissToast: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
  setDemoData: (demoData) => {
    if (get().demoData !== demoData) set({ demoData });
  },
  setPendingAttachment: (pendingAttachment) => set({ pendingAttachment }),
}));

/** Imperative helper usable outside React (e.g. from the API client). */
export const toast = (text: string, tone?: Toast['tone']) => useUi.getState().showToast(text, tone);
