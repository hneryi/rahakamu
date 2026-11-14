/**
 * Chat state machine for one conversation with the coach.
 *
 * `send()` appends the user message and an empty assistant message, then folds
 * SSE events into that assistant message as they arrive:
 *   status → status line + character "thinking"
 *   tool   → recorded for the sources chip
 *   widget → appended inline (generative UI)
 *   token  → streamed text (character "talking")
 *   done   → sources, suggestions, mood (character reacts), message_id for 👍/👎
 * History is persisted on-device per customer (last 40 messages) so a demo can
 * be resumed; only plain text is sent back to the API as context.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import { streamChat } from '@/api/sse';
import type { ChatMessageIn, DoneEvent, Locale, StatusEvent, ToolEvent, Widget } from '@/api/types';
import { useSession } from './session';
import { persistStorage } from './storage';

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  widgets: Widget[];
  tools: ToolEvent[];
  status: StatusEvent | null;
  done: DoneEvent | null;
  error: string | null;
  /** Server-written explanation for a refused request (rate limit, image too large); shown as is. */
  errorDetail?: string | null;
  imageUri: string | null;
  streaming: boolean;
  feedback: 1 | -1 | null;
  offline: boolean;
};

export type ChatStoreState = ChatState;

type ChatState = {
  customerId: string | null;
  messages: ChatMessage[];
  streaming: boolean;
  /** Bumped to make the character celebrate (goal created, quiz solved). */
  celebrateAt: number;
  /** `opts.locale` overrides the UI locale (a question spoken in another language via the FI / EN / SV pill). */
  send: (text: string, image?: { uri: string; base64: string } | null, opts?: { locale?: Locale }) => Promise<void>;
  stop: () => void;
  reset: () => void;
  ensureCustomer: (id: string) => void;
  setFeedback: (id: string, rating: 1 | -1) => void;
  celebrate: () => void;
};

let controller: AbortController | null = null;
const uid = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

const blank = (role: ChatMessage['role'], text = ''): ChatMessage => ({
  id: uid(),
  role,
  text,
  widgets: [],
  tools: [],
  status: null,
  done: null,
  error: null,
  imageUri: null,
  streaming: false,
  feedback: null,
  offline: false,
});

export const useChat = create<ChatState>()(
  persist(
    (set, get) => {
      const patch = (id: string, fn: (m: ChatMessage) => ChatMessage) => set({ messages: get().messages.map((m) => (m.id === id ? fn(m) : m)) });

      return {
        customerId: null,
        messages: [],
        streaming: false,
        celebrateAt: 0,

        ensureCustomer: (id) => {
          if (get().customerId !== id) {
            controller?.abort();
            set({ customerId: id, messages: [], streaming: false });
          }
        },

        send: async (text, image, opts) => {
          const session = useSession.getState();
          const customerId = session.customerId ?? 'CUST05020';
          get().ensureCustomer(customerId);
          if (get().streaming) get().stop();
          const user = { ...blank('user', text), imageUri: image?.uri ?? null };
          const bot = { ...blank('assistant'), streaming: true };
          const history: ChatMessageIn[] = [...get().messages, user]
            .filter((m) => m.text.trim() && !m.error)
            .slice(-12)
            .map((m) => ({ role: m.role, content: m.text }));
          set({ messages: [...get().messages, user, bot], streaming: true });

          controller = new AbortController();
          const signal = controller.signal;
          try {
            await streamChat(
              { customer_id: customerId, persona: session.persona, locale: opts?.locale ?? session.locale, messages: history, image_base64: image?.base64 ?? null },
              {
                onFallback: () => patch(bot.id, (m) => ({ ...m, offline: true })),
                onEvent: (ev) => {
                  switch (ev.event) {
                    case 'status':
                      patch(bot.id, (m) => ({ ...m, status: ev.data }));
                      break;
                    case 'tool':
                      patch(bot.id, (m) => ({ ...m, tools: [...m.tools, ev.data] }));
                      break;
                    case 'widget':
                      patch(bot.id, (m) => (m.widgets.some((w) => w.id === ev.data.id) ? m : { ...m, widgets: [...m.widgets, ev.data] }));
                      break;
                    case 'token':
                      patch(bot.id, (m) => ({ ...m, text: m.text + (ev.data.text ?? ''), status: m.status?.state === 'writing' ? m.status : { state: 'writing', label: '' } }));
                      break;
                    case 'done':
                      patch(bot.id, (m) => ({ ...m, done: ev.data, streaming: false, status: null }));
                      break;
                    case 'error':
                      patch(bot.id, (m) => ({
                        ...m,
                        error: ev.data.message || 'error',
                        errorDetail: ev.data.status && ev.data.status >= 400 && ev.data.status < 500 && ev.data.message ? ev.data.message : null,
                        streaming: false,
                        status: null,
                      }));
                      break;
                  }
                },
              },
              signal,
            );
          } finally {
            patch(bot.id, (m) => ({ ...m, streaming: false, status: null }));
            if (controller?.signal === signal) controller = null;
            set({ streaming: false });
          }
        },

        stop: () => {
          controller?.abort();
          controller = null;
          set({ streaming: false, messages: get().messages.map((m) => (m.streaming ? { ...m, streaming: false, status: null } : m)) });
        },

        reset: () => {
          controller?.abort();
          set({ messages: [], streaming: false });
        },

        setFeedback: (id, rating) => patch(id, (m) => ({ ...m, feedback: rating })),

        celebrate: () => set({ celebrateAt: Date.now() }),
      };
    },
    {
      name: 'spankkibot.chat.v1',
      storage: persistStorage,
      partialize: (s) => ({ customerId: s.customerId, messages: s.messages.slice(-40).map((m) => ({ ...m, streaming: false, status: null, imageUri: m.imageUri?.startsWith('data:') ? null : m.imageUri })) }),
    },
  ),
);
