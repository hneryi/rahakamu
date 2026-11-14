/**
 * REST client for the SPankkiBot backend (SPEC §3.2).
 *
 * Design choices:
 * - **One typed function per endpoint** (`api.*`) so screens never build URLs.
 * - **Graceful degradation**: with `EXPO_PUBLIC_MOCK=1` everything is served from
 *   `fixtures.ts`. Without it, a network failure, a short timeout or a 5xx falls
 *   back to the fixtures and raises the global "demo data" flag (badge in the
 *   UI). While down, `/health` is probed every few seconds; the moment it
 *   answers, the flag is cleared and every query refetches from the real API.
 *   4xx errors are real errors and are thrown.
 * - **Base URL resolution** needs no config in any setup: explicit
 *   `EXPO_PUBLIC_API_URL` wins; on the web a page that is not on localhost talks
 *   to its own origin (production serves the app and `/api` from one host, which
 *   also keeps the S-mobiili web view free of CORS and mixed content); a page on
 *   localhost uses port 8000; on a phone running Expo Go we reuse the dev
 *   machine's LAN IP from the Metro host URI; on the Android emulator
 *   `localhost` is rewritten to `10.0.2.2` (the host loopback alias).
 */
import Constants from 'expo-constants';
import { Platform } from 'react-native';

import { useUi } from '@/store/ui';
import * as fx from './fixtures';
import type {
  BasketsResult,
  Benchmarks,
  DemoCustomer,
  Goal,
  GoalCreate,
  GoalPlan,
  GoalPlanRequest,
  GoalUpdate,
  Health,
  HomeReadiness,
  Lesson,
  Locale,
  Nudge,
  Overview,
  RecurringResult,
  SafeToSpend,
  SpenderProfile,
  SpendingQuery,
  SpendingResult,
  SurvivalPlan,
  TransactionQuery,
  TransactionsResult,
  WhatIfRequest,
  WhatIfResult,
} from './types';

export const MOCK = process.env.EXPO_PUBLIC_MOCK === '1' || process.env.EXPO_PUBLIC_MOCK === 'true';

function resolveBaseUrl(): string {
  const explicit = process.env.EXPO_PUBLIC_API_URL;
  if (explicit) return explicit.replace(/\/$/, '');
  if (Platform.OS === 'web') {
    const loc = typeof window !== 'undefined' ? window.location : undefined;
    const host = loc?.hostname || 'localhost';
    const local = host === 'localhost' || host === '127.0.0.1' || host === '[::1]';
    // Deployed: the API lives under /api on the page's own origin.
    if (!local && loc?.origin && loc.origin !== 'null') return loc.origin;
    return `http://${host}:8000`;
  }
  const hostUri = Constants.expoConfig?.hostUri; // e.g. "192.168.1.20:8081" in Expo Go / dev builds
  const lanHost = hostUri?.split(':')[0];
  if (lanHost && lanHost !== 'localhost' && lanHost !== '127.0.0.1') return `http://${lanHost}:8000`;
  return Platform.OS === 'android' ? 'http://10.0.2.2:8000' : 'http://localhost:8000';
}

export const API_BASE = resolveBaseUrl();
export const API_URL = `${API_BASE}/api`;

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const REQUEST_TIMEOUT_MS = 6000;
const PROBE_TIMEOUT_MS = 3000;
const PROBE_EVERY_MS = 4000;

/** True after a network-level failure, until a health probe succeeds. */
let down = false;
let probeTimer: ReturnType<typeof setTimeout> | null = null;
const recoveryListeners = new Set<() => void>();

export function isApiDown(): boolean {
  return MOCK || down;
}

/** Subscribe to "the API is back" (used to refetch everything that was served from fixtures). */
export function onApiRecovered(cb: () => void): () => void {
  recoveryListeners.add(cb);
  return () => {
    recoveryListeners.delete(cb);
  };
}

async function probe(): Promise<void> {
  probeTimer = null;
  if (!down) return;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}/health`, { headers: { Accept: 'application/json' }, signal: controller.signal });
    const body = res.ok ? ((await res.json()) as { status?: string; ready?: boolean }) : null;
    if (body && body.status === 'ok' && body.ready !== false) {
      markApiUp();
      return;
    }
  } catch {
    /* still down */
  } finally {
    clearTimeout(timer);
  }
  if (down && !probeTimer) probeTimer = setTimeout(probe, PROBE_EVERY_MS);
}

export function markApiDown(): void {
  if (MOCK) return;
  down = true;
  useUi.getState().setDemoData(true);
  if (!probeTimer) probeTimer = setTimeout(probe, PROBE_EVERY_MS);
}

export function markApiUp(): void {
  if (MOCK) return;
  const wasDown = down;
  down = false;
  if (probeTimer) {
    clearTimeout(probeTimer);
    probeTimer = null;
  }
  useUi.getState().setDemoData(false);
  if (wasDown) recoveryListeners.forEach((cb) => cb());
}

type Query = Record<string, string | number | boolean | null | undefined>;

function qs(query?: Query): string {
  if (!query) return '';
  const parts = Object.entries(query)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
  return parts.length ? `?${parts.join('&')}` : '';
}

type RequestOpts = { method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'; body?: unknown; query?: Query; timeoutMs?: number };

/**
 * Perform a JSON request, falling back to `fallback()` when the backend is
 * unreachable. Fixture answers are delayed slightly so loading states are visible
 * and realistic in demos.
 */
async function request<T>(path: string, opts: RequestOpts, fallback: () => T): Promise<T> {
  if (isApiDown()) {
    if (MOCK) useUi.getState().setDemoData(true);
    await new Promise((r) => setTimeout(r, 120));
    return fallback();
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_URL}${path}${qs(opts.query)}`, {
      method: opts.method ?? 'GET',
      headers: opts.body !== undefined ? { 'Content-Type': 'application/json', Accept: 'application/json' } : { Accept: 'application/json' },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: controller.signal,
    });
    if (res.status >= 500) throw new ApiError(`Server error ${res.status}`, res.status);
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const j = (await res.json()) as { detail?: unknown };
        if (j?.detail) detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(detail || `HTTP ${res.status}`, res.status);
    }
    markApiUp();
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (e) {
    if (e instanceof ApiError && e.status < 500) throw e;
    // Network error, timeout or 5xx → keep the demo alive with local data.
    markApiDown();
    return fallback();
  } finally {
    clearTimeout(timer);
  }
}

const c = (id: string) => `/customers/${encodeURIComponent(id)}`;

/** Typed endpoint map. Every customer route takes `locale`: labels, explanations and summaries come back localised. */
export const api = {
  health: () => request<Health>('/health', { timeoutMs: 4000 }, () => ({ status: 'demo', as_of: fx.AS_OF, llm: { primary: false } })),
  demoCustomers: (locale: Locale) => request<DemoCustomer[]>('/customers/demo', { query: { locale } }, () => fx.fixtureDemoCustomers(locale)),
  overview: (id: string, locale: Locale) => request<Overview>(`${c(id)}/overview`, { query: { locale } }, () => fx.fixtureOverview(id, locale)),
  transactions: (id: string, q: TransactionQuery, locale: Locale) =>
    request<TransactionsResult>(`${c(id)}/transactions`, { query: { ...q, locale } }, () => fx.fixtureTransactions(id, q)),
  spending: (id: string, q: SpendingQuery, locale: Locale) => request<SpendingResult>(`${c(id)}/spending`, { query: { ...q, locale } }, () => fx.fixtureSpending(id, q)),
  baskets: (id: string, months: number, locale: Locale) => request<BasketsResult>(`${c(id)}/baskets`, { query: { months, locale } }, () => fx.fixtureBaskets(id, months, locale)),
  safeToSpend: (id: string, locale: Locale) => request<SafeToSpend>(`${c(id)}/safe-to-spend`, { query: { locale } }, () => fx.fixtureSafeToSpend(id, locale)),
  recurring: (id: string, locale: Locale) => request<RecurringResult>(`${c(id)}/recurring`, { query: { locale } }, () => fx.fixtureRecurring(id)),
  profile: (id: string, locale: Locale) => request<SpenderProfile>(`${c(id)}/profile`, { query: { locale } }, () => fx.fixtureProfile(id, locale)),
  benchmarks: (id: string, locale: Locale) => request<Benchmarks>(`${c(id)}/benchmarks`, { query: { locale } }, () => fx.fixtureBenchmarks(id)),
  whatIf: (id: string, body: WhatIfRequest, locale: Locale) =>
    request<WhatIfResult>(`${c(id)}/what-if`, { method: 'POST', body, query: { locale } }, () => fx.fixtureWhatIf(id, body)),
  goals: (id: string, locale: Locale) => request<Goal[]>(`${c(id)}/goals`, { query: { locale } }, () => fx.fixtureGoals(id, locale)),
  createGoal: (id: string, body: GoalCreate) => request<Goal>(`${c(id)}/goals`, { method: 'POST', body }, () => fx.fixtureCreateGoal(id, body)),
  updateGoal: (id: string, goalId: string, body: GoalUpdate) =>
    request<Goal>(`${c(id)}/goals/${encodeURIComponent(goalId)}`, { method: 'PATCH', body }, () => fx.fixtureUpdateGoal(id, goalId, body)),
  deleteGoal: (id: string, goalId: string) =>
    request<unknown>(`${c(id)}/goals/${encodeURIComponent(goalId)}`, { method: 'DELETE' }, () => fx.fixtureDeleteGoal(id, goalId)),
  planGoal: (id: string, body: GoalPlanRequest, locale: Locale) =>
    request<GoalPlan>(`${c(id)}/goals/plan`, { method: 'POST', body, query: { locale } }, () => fx.fixturePlanGoal(id, body, locale)),
  survival: (id: string, locale: Locale, amount?: number, until?: string) =>
    request<SurvivalPlan>(`${c(id)}/survival`, { query: { amount, until, locale } }, () => fx.fixtureSurvival(id, amount, until, locale)),
  homeReadiness: (id: string, locale: Locale, propertyPrice?: number) =>
    request<HomeReadiness>(`${c(id)}/home-readiness`, { query: { property_price: propertyPrice, locale } }, () => fx.fixtureHomeReadiness(id, propertyPrice, locale)),
  nudges: (id: string, locale: Locale) => request<Nudge[]>(`${c(id)}/nudges`, { query: { locale } }, () => fx.fixtureNudges(id, locale)),
  lessons: (locale: Locale) => request<Lesson[] | { lessons: Lesson[] }>('/lessons', { query: { locale } }, () => fx.fixtureLessons(locale)),
  feedback: (messageId: string, rating: 1 | -1, comment?: string) =>
    request<unknown>('/chat/feedback', { method: 'POST', body: { message_id: messageId, rating, comment } }, () => ({ ok: true })),
};
