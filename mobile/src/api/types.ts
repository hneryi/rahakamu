/**
 * TypeScript mirror of the SPankkiBot REST + SSE contract (docs/SPEC.md §3–§5.3).
 *
 * These types are the single client-side source of truth for the backend's JSON.
 * Field names intentionally use the backend's snake_case so payloads can be passed
 * straight through without mapping layers — fewer moving parts, and the same
 * shapes appear in the agent's widgets, the REST endpoints and the fixtures.
 * If the backend contract changes, change it here first and let `tsc` show every
 * component that needs to follow.
 */

export type Locale = 'en' | 'fi' | 'sv';
export type PersonaId = 'sisu' | 'aava';
export type BasketKey = 'fixed' | 'irregular' | 'leak';
export type Basket = BasketKey | 'income' | 'saving';
export type Mood = 'happy' | 'neutral' | 'concerned' | 'celebrate';

// ───────────────────────── Core records ─────────────────────────

export type Tx = {
  id: string;
  date: string;
  timestamp: string;
  amount: number;
  category: string;
  basket: Basket;
  merchant_id: string | null;
  merchant_label: string;
  mcc: number | null;
  mcc_label: string | null;
  icon: string;
  balance_after: number;
  type: string;
};

export type GoalKind = 'car' | 'travel' | 'home' | 'emergency' | 'education' | 'gadget' | 'other';

export type Goal = {
  id: string;
  name: string;
  emoji: string;
  kind: GoalKind;
  target_amount: number;
  saved_amount: number;
  deadline: string | null;
  monthly_contribution: number;
  progress: number;
  created_at: string;
  /** Server-computed extras (absent in older payloads and fixtures). */
  remaining?: number;
  months_left?: number | null;
};

export type DemoCustomer = {
  customer_id: string;
  name: string;
  age: number;
  postal_code: string;
  tagline: string;
  avatar_emoji: string;
};

export type Nudge = {
  id: string;
  kind: 'celebrate' | 'warn' | 'tip' | 'goal';
  text: string;
  emoji: string;
  action_prompt: string;
};

export type BalancePoint = { date: string; balance: number };

// ───────────────────────── Analytics payloads ─────────────────────────

export type SafeToSpend = {
  balance: number;
  next_payday: string;
  days_until_payday: number;
  upcoming_bills: { label: string; amount: number; expected_date: string; category?: string; basket?: Basket }[];
  upcoming_bills_total?: number;
  irregular_buffer: number;
  goal_contributions: number;
  safe_total: number;
  safe_per_day: number;
  safe_this_week: number;
  status: 'comfortable' | 'tight' | 'critical';
  explanation: string;
  typical_daily_spend?: number;
  payday_detected_from?: string;
  payday_typical_day?: number | null;
  salary_late?: boolean;
  formula?: string;
};

/** Situation-adaptive recovery state shared by nudges, overview and demo chat. */
export type RecoveryState = 'balance_repair' | 'cashflow_stabilizing' | 'ordinary' | 'unknown';

export type Recovery = {
  state: RecoveryState;
  months: number;
  balance: number | null;
  monthly_income: number | null;
  monthly_spending: number | null;
  monthly_surplus: number | null;
  deficit: number | null;
  goal_monthly_need: number;
  planned_monthly_change: number | null;
  urgency: SafeToSpend['status'] | null;
  safe_per_day: number | null;
  days_until_payday: number;
  goal_contributions: number;
  goal_reservations_present: boolean;
  tx_count: number;
  period: string;
};

export type Overview = {
  customer: { id: string; name: string; age: number; postal_code: string; avatar_emoji?: string };
  as_of: string;
  balance: number;
  trend_30d: BalancePoint[];
  month: {
    month?: string;
    income: number;
    spent: number;
    saved: number;
    by_basket: Record<BasketKey, number>;
  };
  safe_to_spend: SafeToSpend;
  recovery?: Recovery;
  goals: Goal[];
  recent_transactions: Tx[];
  nudges: Nudge[];
};

export type SpendingGroupBy =
  | 'none'
  | 'category'
  | 'basket'
  | 'month'
  | 'week'
  | 'weekday'
  | 'merchant'
  | 'hour'
  | 'day';

export type SpendingQuery = {
  start?: string;
  end?: string;
  category?: string;
  basket?: Basket;
  merchant?: string;
  group_by?: SpendingGroupBy;
};

export type SpendingResult = {
  filters: Record<string, unknown>;
  total: number;
  count: number;
  avg_tx: number;
  groups: { key: string; label: string; total: number; count: number; share?: number }[];
  period: { start: string; end: string; days?: number };
};

export type TransactionQuery = {
  start?: string;
  end?: string;
  category?: string;
  basket?: Basket;
  merchant?: string;
  text?: string;
  limit?: number;
  offset?: number;
};

export type TransactionsResult = { items: Tx[]; total_count: number; limit?: number; offset?: number };

export type BasketMonth = {
  month: string;
  fixed: number;
  irregular: number;
  leak: number;
  income: number;
  saving: number;
  spent?: number;
  tx_count?: number;
  /** True for the month that is still running (as_of is mid-month). */
  partial?: boolean;
};

export type LabelTotal = { label: string; total: number; category?: string; count?: number };

export type BasketsResult = {
  months: BasketMonth[];
  current_month: BasketMonth & { top: Record<BasketKey, LabelTotal[]>; shares?: Partial<Record<BasketKey, number>> };
  explanations: Record<BasketKey, string>;
  average_complete_month?: Partial<Record<BasketKey | 'income' | 'saving' | 'spent', number>>;
  labels?: Partial<Record<Basket, string>>;
  rules?: unknown;
};

export type RecurringItem = {
  label: string;
  category: string;
  merchant_id: string | null;
  avg_amount: number;
  cadence: string;
  day_of_month: number | null;
  last_date: string;
  basket: Basket;
  next_expected?: string | null;
  occurrences?: number;
  monthly_equivalent?: number;
};

export type RecurringResult = { items: RecurringItem[]; monthly_total: number };

export type SpenderProfile = {
  archetype: { key: string; name: string; emoji: string; description: string };
  traits: { key: string; label: string; score: number; detail: string }[];
  savings_rate: number;
  leak_share: number;
  weekend_share: number;
  small_tx_per_week: number;
  late_night_share: number;
  volatility: number;
  /** Extra aggregates the backend may add; never required by the UI. */
  [extra: string]: unknown;
};

export type BenchmarkRow = {
  category: string;
  you_monthly: number;
  peer_median_monthly: number;
  peer_p25: number;
  peer_p75: number;
  percentile: number;
  stat_fi_monthly: number | null;
};

/** Savings rate comparison: fractions (0.12 = 12 %), not euros. */
export type BenchmarkRate = {
  you: number;
  peer_median: number;
  peer_p25?: number;
  peer_p75?: number;
  percentile?: number;
  stat_fi?: number | null;
  note?: string;
};

export type Benchmarks = {
  peer_group: { label: string; size: number; age_band?: string; your_age?: number };
  categories: BenchmarkRow[];
  income?: Partial<BenchmarkRow>;
  savings_rate?: BenchmarkRate;
  highlight?: string | null;
  sources?: { name: string; url: string; note: string }[];
};

export type WhatIfAdjustment = {
  category?: string;
  basket?: Basket;
  merchant?: string;
  change_pct: number;
};

export type WhatIfRequest = {
  adjustments: WhatIfAdjustment[];
  horizon_months?: number;
  invest_return_pct?: number;
};

export type WhatIfResult = {
  baseline_monthly: number;
  new_monthly: number;
  monthly_saving: number;
  horizon_months: number;
  total_saving: number;
  with_return: number;
  invest_return_pct?: number;
  share_of_spending?: number;
  window?: { start: string; end: string; months?: number };
  per_item: {
    label?: string;
    category?: string | null;
    basket?: Basket | null;
    merchant?: string | null;
    mcc?: number | null;
    change_pct?: number;
    baseline_monthly?: number;
    new_monthly?: number;
    monthly_saving?: number;
    yearly_saving?: number;
    tx_count?: number;
  }[];
  series: { month: number; cumulative: number; cumulative_no_return?: number }[];
};

export type GoalCreate = {
  name: string;
  target_amount: number;
  deadline?: string | null;
  emoji?: string | null;
  kind?: GoalKind;
  saved_amount?: number;
};

export type GoalUpdate = Partial<GoalCreate> & { monthly_contribution?: number };

export type GoalPlanRequest = {
  target_amount: number;
  deadline?: string | null;
  name?: string | null;
  saved_amount?: number;
};

export type GoalPlanCut = {
  label: string;
  category: string;
  basket: Basket;
  current_monthly: number;
  cut_pct: number;
  monthly_saving: number;
  why: string;
};

export type GoalPlan = {
  name: string | null;
  target_amount: number;
  saved_amount: number;
  deadline: string | null;
  months: number;
  needed_per_month: number;
  current_monthly_surplus: number;
  remaining?: number;
  monthly_income?: number;
  monthly_spending?: number;
  committed_to_other_goals?: number;
  gap: number;
  feasibility: 'on_track' | 'stretch' | 'unrealistic';
  suggested_deadline: string | null;
  cuts: GoalPlanCut[];
  cuts_total: number;
  summary: string;
};

export type SurvivalPlan = {
  amount: number;
  until: string;
  days: number;
  upcoming_bills_total: number;
  bills: { label: string; amount: number; expected_date?: string; category?: string; basket?: Basket; cadence?: string }[];
  paused_savings?: number;
  amount_mode?: string;
  free_money: number;
  per_day: number;
  per_week: number;
  /** `category` is the raw key; `label` is the localised name to show. */
  category_budgets: { category: string; label?: string; budget: number; typical: number; essential?: boolean }[];
  risk: 'ok' | 'tight' | 'short';
  shortfall: number;
  tips: string[];
};

export type HomeReadiness = {
  property_price: number;
  loan_needed: number;
  equity_needed: number;
  your_equity_estimate: number;
  required_monthly_income: number;
  your_monthly_income: number;
  ltv: number;
  verdict: 'ready' | 'almost' | 'not_yet';
  gaps: string[];
  dataset_note: string;
  customer_application: Record<string, unknown> | null;
  closing_costs_estimate?: number;
  equity_breakdown?: Record<string, number>;
  monthly_payment_estimate?: number;
  stress_test_payment?: number;
  assumptions?: Record<string, unknown>;
  dataset_ratios?: Record<string, unknown>;
};

export type Health = {
  status: string;
  /** False while the dataset is still loading (the API answers 503 on data routes). */
  ready?: boolean;
  as_of: string;
  llm: { primary: boolean; fallback?: boolean; available?: boolean };
  data?: { loaded: boolean; state: string };
};

// ───────────────────────── Lessons (Money Gym) ─────────────────────────

export type Quiz = {
  question: string;
  options: string[];
  answer_index: number;
  explanation?: string;
};

/**
 * Lesson shape served by GET /api/lessons. The spec fixes only the widget subset
 * {id,title,body,emoji,quiz}; the rest is optional metadata used for ranking
 * recommendations. `normalizeLesson` in hooks.ts tolerates missing fields.
 */
export type Lesson = {
  id: string;
  title: string;
  emoji: string;
  body: string;
  summary?: string;
  basket?: BasketKey | null;
  topic?: string;
  /** Difficulty 1–3 (number on the wire). */
  level?: number;
  minutes?: number;
  tags?: string[];
  quiz?: Quiz | null;
  flagship?: boolean;
  key_takeaway?: string;
  unlock_hint?: string;
  order?: number;
};

// ───────────────────────── Chat / SSE (§4.2) ─────────────────────────

export type ChatMessageIn = { role: 'user' | 'assistant'; content: string };

export type ChatRequest = {
  customer_id: string;
  persona: PersonaId;
  locale: Locale;
  messages: ChatMessageIn[];
  image_base64: string | null;
};

export type StatusEvent = { state: 'thinking' | 'tool' | 'writing'; label: string };
export type ToolEvent = { name: string; args: Record<string, unknown>; summary: string };
export type TokenEvent = { text: string };
export type DoneEvent = {
  message_id: string;
  sources: { tx_count: number; period: string; tools: string[] };
  suggestions: string[];
  mood: Mood;
  /** Set when the answer was cut at the output cap. */
  truncated?: boolean;
  /** Set when a safety guardrail rewrote or refused the answer. */
  guardrail?: string;
};
export type ErrorEvent = { message: string; status?: number };

// ───────────────────────── Generative-UI widgets (§5.3) ─────────────────────────

export type KpiData = {
  items: { label: string; value: number; unit: '€' | '%' | ''; delta?: number; tone?: 'good' | 'bad' | 'neutral' }[];
};
export type BarChartData = { title: string; unit: string; bars: { label: string; value: number; highlight?: boolean }[] };
export type LineChartData = { title: string; unit: string; points: { x: string; y: number }[]; target?: number };
export type DonutChartData = { title: string; unit: string; slices: { label: string; value: number; color?: string }[] };
export type BasketBreakdownData = {
  month: string;
  fixed: number;
  irregular: number;
  leak: number;
  explanations: Record<BasketKey, string>;
  top: Record<BasketKey, LabelTotal[]>;
};
export type WhatIfData = {
  base_adjustments: WhatIfAdjustment[];
  result: WhatIfResult;
  slider: { category?: string | null; basket?: Basket | null; merchant?: string | null; min: number; max: number; value: number };
  horizon_months?: number;
  invest_return_pct?: number;
};
export type TransactionListData = { title: string; items: Tx[]; total: number };
export type LessonData = { id: string; title: string; body: string; emoji: string; quiz?: Quiz | null; summary?: string; key_takeaway?: string };
export type ActionButton =
  | { label: string; kind: 'prompt'; payload: string | { prompt?: string; text?: string } }
  | { label: string; kind: 'create_goal'; payload: GoalCreate }
  | { label: string; kind: 'open_tab'; payload: string | { tab?: string } };
export type ActionButtonsData = { buttons: ActionButton[] };

export type WidgetDataMap = {
  kpi: KpiData;
  bar_chart: BarChartData;
  line_chart: LineChartData;
  donut_chart: DonutChartData;
  basket_breakdown: BasketBreakdownData;
  safe_to_spend: SafeToSpend;
  goal_plan: GoalPlan;
  what_if: WhatIfData;
  transaction_list: TransactionListData;
  spender_profile: SpenderProfile;
  benchmark: Benchmarks;
  survival_plan: SurvivalPlan;
  home_readiness: HomeReadiness;
  lesson: LessonData;
  action_buttons: ActionButtonsData;
};

export type WidgetType = keyof WidgetDataMap;

/** A widget as received over SSE. `type` is a string because unknown types must be tolerated. */
export type Widget = { id: string; type: string; data: unknown };

export type KnownWidget = { [K in WidgetType]: { id: string; type: K; data: WidgetDataMap[K] } }[WidgetType];

export type SseEvent =
  | { event: 'status'; data: StatusEvent }
  | { event: 'tool'; data: ToolEvent }
  | { event: 'widget'; data: Widget }
  | { event: 'token'; data: TokenEvent }
  | { event: 'done'; data: DoneEvent }
  | { event: 'error'; data: ErrorEvent };
