/**
 * Streaming chat over Server-Sent Events (SPEC §4.2).
 *
 * `POST /api/chat` answers with `text/event-stream`. Browsers' EventSource only
 * supports GET, so we POST with `fetch` and parse the stream ourselves:
 * - native: `fetch` from `expo/fetch` (WinterCG-compliant, exposes a streaming
 *   `ReadableStream` body; React Native's built-in fetch buffers the whole body),
 * - web: the global `fetch`.
 *
 * The parser is incremental and robust to arbitrary chunk boundaries (a chunk may
 * end mid-line, mid-UTF-8 sequence or between "\r" and "\n"), multi-line `data:`
 * fields and comment/keep-alive lines — real proxies split streams unpredictably.
 *
 * If the backend is unreachable (or mock mode is on) the same callback receives
 * events from the local fixture stream, so the UI code has exactly one path.
 */
import { fetch as expoFetch } from 'expo/fetch';
import { Platform } from 'react-native';

import { API_URL, isApiDown, markApiDown, markApiUp, MOCK } from './client';
import { fixtureChatStream } from './fixtures';
import type { ChatRequest, SseEvent } from './types';

export type RawSseEvent = { event: string; data: string; id?: string };

const KNOWN_EVENTS = new Set(['status', 'tool', 'widget', 'token', 'done', 'error']);

/** Incremental SSE parser (WHATWG event-stream format). */
export class SSEParser {
  private buffer = '';
  private eventName = '';
  private dataLines: string[] = [];
  private lastId: string | undefined;

  /** Feed decoded text; returns any events completed by this chunk. */
  feed(chunk: string): RawSseEvent[] {
    this.buffer += chunk;
    // Hold back a trailing "\r": it may be the first half of a "\r\n" split across chunks.
    let hold = '';
    if (this.buffer.endsWith('\r')) {
      hold = '\r';
      this.buffer = this.buffer.slice(0, -1);
    }
    const lines = this.buffer.replace(/\r\n?/g, '\n').split('\n');
    this.buffer = (lines.pop() ?? '') + hold;
    const out: RawSseEvent[] = [];
    for (const line of lines) this.processLine(line, out);
    return out;
  }

  /** Flush at end of stream: dispatch a final event even without a trailing blank line. */
  flush(): RawSseEvent[] {
    const out: RawSseEvent[] = [];
    if (this.buffer) {
      this.processLine(this.buffer.replace(/\r$/, ''), out);
      this.buffer = '';
    }
    this.processLine('', out);
    return out;
  }

  private processLine(line: string, out: RawSseEvent[]): void {
    if (line === '') {
      if (this.dataLines.length) {
        out.push({ event: this.eventName || 'message', data: this.dataLines.join('\n'), id: this.lastId });
      }
      this.eventName = '';
      this.dataLines = [];
      return;
    }
    if (line.startsWith(':')) return; // comment / keep-alive
    const colon = line.indexOf(':');
    const field = colon === -1 ? line : line.slice(0, colon);
    let value = colon === -1 ? '' : line.slice(colon + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') this.eventName = value;
    else if (field === 'data') this.dataLines.push(value);
    else if (field === 'id') this.lastId = value;
    // "retry" and unknown fields are ignored.
  }
}

/** Convert a raw event into a typed one; unknown event names or bad JSON are dropped. */
export function toTypedEvent(raw: RawSseEvent): SseEvent | null {
  if (!KNOWN_EVENTS.has(raw.event)) return null;
  try {
    return { event: raw.event, data: JSON.parse(raw.data) } as SseEvent;
  } catch {
    return null;
  }
}

export type StreamHandlers = {
  onEvent: (e: SseEvent) => void;
  /** Called once if we switched to the offline fixture stream. */
  onFallback?: () => void;
};

async function runFixture(req: ChatRequest, handlers: StreamHandlers, signal?: AbortSignal) {
  for await (const ev of fixtureChatStream(req, signal)) {
    if (signal?.aborted) return;
    handlers.onEvent(ev);
  }
}

/**
 * Stream one chat turn. Resolves when the stream ends (after `done`/`error`) or
 * is aborted. Never rejects for network problems — it falls back instead.
 */
export async function streamChat(req: ChatRequest, handlers: StreamHandlers, signal?: AbortSignal): Promise<void> {
  if (MOCK || isApiDown()) {
    if (!MOCK) handlers.onFallback?.();
    return runFixture(req, handlers, signal);
  }

  const doFetch = (Platform.OS === 'web' ? globalThis.fetch : expoFetch) as typeof globalThis.fetch;
  let gotEvent = false;
  try {
    const res = await doFetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify(req),
      signal,
    });
    if (!res.ok) {
      if (res.status >= 500) throw new Error(`HTTP ${res.status}`);
      // 4xx (429 rate limit, 413 image too large, 422 bad input): the backend explains itself in `detail`.
      let message = `HTTP ${res.status}`;
      try {
        const j = (await res.json()) as { detail?: unknown };
        if (typeof j?.detail === 'string' && j.detail) message = j.detail;
      } catch {
        /* non-JSON error body */
      }
      handlers.onEvent({ event: 'error', data: { message, status: res.status } });
      return;
    }
    markApiUp();
    const parser = new SSEParser();
    const emit = (raws: RawSseEvent[]) => {
      for (const raw of raws) {
        const ev = toTypedEvent(raw);
        if (ev) {
          gotEvent = true;
          handlers.onEvent(ev);
        }
      }
    };
    const body = res.body as ReadableStream<Uint8Array> | null;
    if (body && typeof body.getReader === 'function') {
      const reader = body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        if (value) emit(parser.feed(decoder.decode(value, { stream: true })));
      }
      emit(parser.feed(decoder.decode()));
    } else {
      // Environments without streaming bodies: degrade to whole-body parsing.
      emit(parser.feed(await res.text()));
    }
    emit(parser.flush());
  } catch (e) {
    if (signal?.aborted) return;
    if (gotEvent) {
      handlers.onEvent({ event: 'error', data: { message: e instanceof Error ? e.message : 'Stream interrupted' } });
      return;
    }
    // Could not reach the agent at all → offline demo mode.
    markApiDown();
    handlers.onFallback?.();
    await runFixture(req, handlers, signal);
  }
}
