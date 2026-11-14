/**
 * Deep-link helpers into the chat screen. Every "Ask about this" button in the
 * app funnels through here, so the conversation entry points stay consistent
 * (prefill only vs. auto-send) and are easy to wire from S-mobiili too:
 * `spankkibot://chat?q=...&send=1` opens the same flow from outside the app.
 */
import { router } from 'expo-router';

export function openChat(question?: string, opts: { send?: boolean; voice?: boolean; lang?: string } = {}): void {
  const params: Record<string, string> = {};
  if (question) params.q = question;
  if (opts.send ?? !!question) params.send = '1';
  // Asked by voice: the chat reads the answer aloud and sends in the spoken language.
  if (opts.voice) params.voice = '1';
  if (opts.lang) params.lang = opts.lang;
  router.push({ pathname: '/chat', params });
}
