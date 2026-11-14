/**
 * TanStack Query hooks — the only way screens read server state.
 *
 * Why TanStack Query: caching + de-duplication means Home, Insights and Chat can
 * all ask for "overview" without triple-fetching; mutations (create goal from a
 * chat widget, edit on the Goals tab) invalidate one key and every screen
 * refreshes. Keys always include the customer id (switching demo customer never
 * shows stale data) and the locale where text comes back localised.
 */
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { useSession } from '@/store/session';
import { api } from './client';
import type { GoalCreate, GoalPlanRequest, GoalUpdate, Lesson, Locale, SpendingQuery, TransactionQuery, WhatIfRequest } from './types';

const STALE = 60_000;

function useIds(): { id: string; locale: Locale } {
  const id = useSession((s) => s.customerId) ?? 'CUST05020';
  const locale = useSession((s) => s.locale);
  return { id, locale };
}

export const qk = {
  overview: (id: string, l: Locale) => ['overview', id, l] as const,
  goals: (id: string) => ['goals', id] as const,
  customer: (id: string) => ['customer', id] as const,
};

export function useHealth() {
  return useQuery({ queryKey: ['health'], queryFn: api.health, staleTime: 30_000, retry: false });
}

export function useDemoCustomers() {
  const locale = useSession((s) => s.locale);
  return useQuery({ queryKey: ['demo-customers', locale], queryFn: () => api.demoCustomers(locale), staleTime: Infinity });
}

export function useOverview() {
  const { id, locale } = useIds();
  return useQuery({ queryKey: qk.overview(id, locale), queryFn: () => api.overview(id, locale), staleTime: STALE });
}

export function useBaskets(months: number) {
  const { id, locale } = useIds();
  return useQuery({
    queryKey: ['customer', id, 'baskets', months, locale],
    queryFn: () => api.baskets(id, months, locale),
    staleTime: STALE,
    placeholderData: keepPreviousData,
  });
}

export function useSpending(q: SpendingQuery, enabled = true) {
  const { id, locale } = useIds();
  return useQuery({
    queryKey: ['customer', id, 'spending', q, locale],
    queryFn: () => api.spending(id, q, locale),
    staleTime: STALE,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useTransactions(q: TransactionQuery, enabled = true) {
  const { id, locale } = useIds();
  return useQuery({ queryKey: ['customer', id, 'transactions', q, locale], queryFn: () => api.transactions(id, q, locale), staleTime: STALE, enabled });
}

export function useRecurring() {
  const { id, locale } = useIds();
  return useQuery({ queryKey: ['customer', id, 'recurring', locale], queryFn: () => api.recurring(id, locale), staleTime: STALE });
}

export function useProfile() {
  const { id, locale } = useIds();
  return useQuery({ queryKey: ['customer', id, 'profile', locale], queryFn: () => api.profile(id, locale), staleTime: STALE });
}

export function useBenchmarks() {
  const { id, locale } = useIds();
  return useQuery({ queryKey: ['customer', id, 'benchmarks', locale], queryFn: () => api.benchmarks(id, locale), staleTime: STALE });
}

export function useGoals() {
  const { id, locale } = useIds();
  return useQuery({ queryKey: [...qk.goals(id), locale], queryFn: () => api.goals(id, locale), staleTime: STALE });
}

/** Live goal-plan preview used while the user types in the create-goal sheet. */
export function useGoalPlan(req: GoalPlanRequest | null) {
  const { id, locale } = useIds();
  return useQuery({
    queryKey: ['customer', id, 'goal-plan', req, locale],
    queryFn: () => api.planGoal(id, req as GoalPlanRequest, locale),
    enabled: !!req && req.target_amount > 0,
    placeholderData: keepPreviousData,
    staleTime: STALE,
  });
}

function useInvalidateGoals() {
  const qc = useQueryClient();
  const { id } = useIds();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: qk.goals(id) }),
      qc.invalidateQueries({ queryKey: ['overview', id] }),
      qc.invalidateQueries({ queryKey: ['customer', id, 'goal-plan'] }),
    ]);
}

export function useCreateGoal() {
  const { id } = useIds();
  const invalidate = useInvalidateGoals();
  return useMutation({ mutationFn: (body: GoalCreate) => api.createGoal(id, body), onSuccess: invalidate });
}

export function useUpdateGoal() {
  const { id } = useIds();
  const invalidate = useInvalidateGoals();
  return useMutation({ mutationFn: (v: { goalId: string; patch: GoalUpdate }) => api.updateGoal(id, v.goalId, v.patch), onSuccess: invalidate });
}

export function useDeleteGoal() {
  const { id } = useIds();
  const invalidate = useInvalidateGoals();
  return useMutation({ mutationFn: (goalId: string) => api.deleteGoal(id, goalId), onSuccess: invalidate });
}

export function useWhatIf() {
  const { id, locale } = useIds();
  return useMutation({ mutationFn: (body: WhatIfRequest) => api.whatIf(id, body, locale) });
}

export function useNudges() {
  const { id, locale } = useIds();
  return useQuery({ queryKey: ['customer', id, 'nudges', locale], queryFn: () => api.nudges(id, locale), staleTime: STALE });
}

/** Tolerant normaliser: the lessons file may evolve; never crash the Learn tab on shape drift. */
export function normalizeLesson(raw: unknown, i: number): Lesson | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const str = (v: unknown) => (typeof v === 'string' ? v : undefined);
  const title = str(r.title) ?? str(r.name);
  const body = str(r.body) ?? str(r.content) ?? str(r.text) ?? '';
  if (!title) return null;
  const rawQuiz = (Array.isArray(r.quiz) ? r.quiz[0] : r.quiz) ?? (Array.isArray(r.quizzes) ? r.quizzes[0] : undefined);
  let quiz: Lesson['quiz'] = null;
  if (rawQuiz && typeof rawQuiz === 'object') {
    const q = rawQuiz as Record<string, unknown>;
    const options = Array.isArray(q.options) ? q.options.map(String) : [];
    const answer = typeof q.answer_index === 'number' ? q.answer_index : typeof q.answer === 'number' ? q.answer : 0;
    if (str(q.question) && options.length >= 2) quiz = { question: String(q.question), options, answer_index: answer, explanation: str(q.explanation) };
  }
  return {
    id: str(r.id) ?? `lesson-${i}`,
    title,
    emoji: str(r.emoji) ?? '📘',
    body,
    summary: str(r.summary) ?? str(r.subtitle) ?? body.split('\n')[0]?.replace(/\*\*/g, '').slice(0, 90),
    basket: (str(r.basket) as Lesson['basket']) ?? null,
    topic: str(r.topic),
    level: typeof r.level === 'number' ? r.level : undefined,
    minutes: typeof r.minutes === 'number' ? r.minutes : undefined,
    tags: Array.isArray(r.tags) ? r.tags.map(String) : undefined,
    quiz,
    flagship: r.flagship === true,
    key_takeaway: str(r.key_takeaway),
    unlock_hint: str(r.unlock_hint),
    order: typeof r.order === 'number' ? r.order : undefined,
  };
}

export function useLessons() {
  const { locale } = useIds();
  return useQuery({
    queryKey: ['lessons', locale],
    queryFn: async () => {
      const res = await api.lessons(locale);
      const list: unknown[] = Array.isArray(res) ? res : Array.isArray((res as { lessons?: unknown[] })?.lessons) ? (res as { lessons: unknown[] }).lessons : [];
      return list.map(normalizeLesson).filter((l): l is Lesson => !!l);
    },
    staleTime: Infinity,
  });
}

export function useFeedback() {
  return useMutation({ mutationFn: (v: { messageId: string; rating: 1 | -1 }) => api.feedback(v.messageId, v.rating) });
}
