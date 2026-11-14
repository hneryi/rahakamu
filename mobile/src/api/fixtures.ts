/**
 * Offline demo engine.
 *
 * Why this exists: hackathon demos die on flaky Wi-Fi. With `EXPO_PUBLIC_MOCK=1`,
 * or automatically when the API is unreachable, every endpoint is answered from
 * here and the UI shows a small "demo data" badge. It is not a static JSON dump:
 * we generate a deterministic, realistic transaction history per demo customer
 * (seeded PRNG, so numbers are stable between reloads) and compute the same
 * analytics the backend does — baskets, safe-to-spend, what-if, goal plans,
 * survival plan — with simplified versions of the backend's rules (SPEC §2–§3).
 * The chat fixture streams real SSE-shaped events (status → tool → widget →
 * token → done) so the generative-UI pipeline is exercised end to end.
 *
 * All merchant names are generic ("Café #12") — never real brands — matching
 * the backend's privacy rule.
 */
import { detectLanguage } from '@/lib/speechLang';
import type {
  Basket,
  BasketKey,
  BasketsResult,
  Benchmarks,
  ChatRequest,
  DemoCustomer,
  Goal,
  GoalCreate,
  GoalKind,
  GoalPlan,
  GoalPlanRequest,
  GoalUpdate,
  HomeReadiness,
  Lesson,
  Locale,
  Nudge,
  Overview,
  RecurringItem,
  RecurringResult,
  Recovery,
  SafeToSpend,
  SpenderProfile,
  SpendingQuery,
  SpendingResult,
  SseEvent,
  SurvivalPlan,
  TransactionQuery,
  TransactionsResult,
  Tx,
  WhatIfRequest,
  WhatIfResult,
  Widget,
} from './types';

export const AS_OF = '2026-09-18';
const HISTORY_START = '2026-01-01';

// ───────────────────────── deterministic randomness ─────────────────────────

function hashSeed(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const r2 = (n: number) => Math.round(n * 100) / 100;

// ───────────────────────── date helpers (UTC, ISO strings) ─────────────────────────

const toDate = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`);
const iso = (d: Date) => d.toISOString().slice(0, 10);
const addDays = (s: string, n: number) => {
  const d = toDate(s);
  d.setUTCDate(d.getUTCDate() + n);
  return iso(d);
};
const addMonths = (s: string, n: number) => {
  const d = toDate(s);
  d.setUTCMonth(d.getUTCMonth() + n);
  return iso(d);
};
const diffDays = (a: string, b: string) => Math.round((toDate(b).getTime() - toDate(a).getTime()) / 86_400_000);
const monthKey = (s: string) => s.slice(0, 7);
const monthStart = (s: string) => `${s.slice(0, 7)}-01`;

/** Next date strictly after `from` that falls on `day` of a month (clamped to month length). */
function nextDayOfMonth(from: string, day: number): string {
  for (let i = 1; i <= 62; i++) {
    const c = addDays(from, i);
    const d = toDate(c);
    const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate();
    if (d.getUTCDate() === Math.min(day, last)) return c;
  }
  return addDays(from, 30);
}

// ───────────────────────── demo customers ─────────────────────────

type Spend = { cat: string; mcc: number; perMonth: number; avg: number; spread: number; prefix: string; label: string; icon: string; night?: boolean; weekend?: boolean };

type ProfileCfg = {
  customer: DemoCustomer;
  archetype: SpenderProfile['archetype']['key'];
  payday: number;
  salary: number;
  otherIncome?: { day: number; amount: number };
  rent: number;
  electricity: number;
  phone: number;
  streaming: number[];
  transit: number;
  gym?: number;
  saving: number;
  groceriesPerWeek: number;
  groceryAvg: number;
  spends: Spend[];
  finalBalance: number;
  goals: Omit<Goal, 'progress' | 'created_at' | 'monthly_contribution'>[];
};

const S = (cat: string, mcc: number, perMonth: number, avg: number, prefix: string, label: string, icon: string, extra: Partial<Spend> = {}): Spend => ({
  cat,
  mcc,
  perMonth,
  avg,
  spread: 0.45,
  prefix,
  label,
  icon,
  ...extra,
});

const PROFILES: Record<string, ProfileCfg> = {
  CUST05020: {
    customer: { customer_id: 'CUST05020', name: 'Emma', age: 21, postal_code: '00530', tagline: 'Student & part-time barista — small income, leaky spending', avatar_emoji: '🎓' },
    archetype: 'latte_leaker',
    payday: 15,
    salary: 1090,
    otherIncome: { day: 3, amount: 268.28 },
    rent: 545,
    electricity: 32,
    phone: 19.9,
    streaming: [11.99, 6.99],
    transit: 33.6,
    saving: 0,
    groceriesPerWeek: 2.5,
    groceryAvg: 21,
    spends: [
      S('Restaurants', 5814, 14, 9.5, 'RES', 'Café', '☕', { spread: 0.5 }),
      S('Restaurants', 5812, 4, 21, 'RES', 'Restaurant', '🍽️'),
      S('Restaurants', 5813, 3, 24, 'BAR', 'Bar', '🍸', { night: true, weekend: true }),
      S('Groceries', 5499, 9, 5.4, 'KIO', 'Kiosk', '🏪'),
      S('Transportation', 4121, 2.5, 17, 'TAX', 'Taxi', '🚕', { night: true, weekend: true }),
      S('Entertainment', 7832, 2, 13, 'ENT', 'Cinema', '🎬', { weekend: true }),
      S('Lifestyle', 5651, 2.5, 36, 'LIF', 'Clothing store', '👕'),
      S('Lifestyle', 5999, 2, 14, 'LIF', 'Shop', '🛍️'),
      S('Health', 5912, 0.7, 16, 'PHA', 'Pharmacy', '💊'),
    ],
    finalBalance: 1138.42,
    goals: [
      { id: 'g-emma-1', name: 'Emergency fund', emoji: '🛟', kind: 'emergency', target_amount: 1000, saved_amount: 180, deadline: '2027-06-30' },
      { id: 'g-emma-2', name: 'Interrail summer', emoji: '🚆', kind: 'travel', target_amount: 900, saved_amount: 240, deadline: '2027-05-31' },
    ],
  },
  CUST00584: {
    customer: { customer_id: 'CUST00584', name: 'Leo', age: 22, postal_code: '33100', tagline: 'First job, balance dips below zero before payday', avatar_emoji: '🛹' },
    archetype: 'tightrope_walker',
    payday: 25,
    salary: 1742,
    rent: 690,
    electricity: 38,
    phone: 24.9,
    streaming: [13.99, 10.99, 7.99],
    transit: 55.3,
    gym: 29.9,
    saving: 0,
    groceriesPerWeek: 2,
    groceryAvg: 28,
    spends: [
      S('Restaurants', 5814, 10, 12.5, 'FST', 'Fast food', '🍔', { night: true }),
      S('Restaurants', 5813, 4, 31, 'BAR', 'Bar', '🍺', { night: true, weekend: true }),
      S('Groceries', 5499, 8, 6.2, 'KIO', 'Kiosk', '🏪', { night: true }),
      S('Transportation', 4121, 3, 21, 'TAX', 'Taxi', '🚕', { night: true, weekend: true }),
      S('Entertainment', 7999, 3, 22, 'ENT', 'Gaming', '🎮'),
      S('Home & Tech', 5732, 0.6, 79, 'TEC', 'Electronics store', '🎧'),
      S('Lifestyle', 5941, 1, 45, 'LIF', 'Sports store', '👟'),
    ],
    finalBalance: 63.4,
    goals: [
      { id: 'g-leo-1', name: 'Payday buffer', emoji: '🛟', kind: 'emergency', target_amount: 500, saved_amount: 40, deadline: '2027-03-31' },
      { id: 'g-leo-2', name: 'New laptop', emoji: '💻', kind: 'gadget', target_amount: 1200, saved_amount: 150, deadline: '2027-08-31' },
    ],
  },
  CUST00586: {
    customer: { customer_id: 'CUST00586', name: 'Mika', age: 39, postal_code: '02100', tagline: 'High income, big leaks — ready to invest smarter', avatar_emoji: '🚀' },
    archetype: 'weekend_treater',
    payday: 15,
    salary: 5240,
    rent: 1480,
    electricity: 74,
    phone: 29.9,
    streaming: [17.99, 13.99, 11.99, 9.99],
    transit: 0,
    gym: 59,
    saving: 300,
    groceriesPerWeek: 2.5,
    groceryAvg: 62,
    spends: [
      S('Restaurants', 5812, 9, 48, 'RES', 'Restaurant', '🍽️', { weekend: true }),
      S('Restaurants', 5814, 12, 11, 'RES', 'Café', '☕'),
      S('Restaurants', 5813, 4, 52, 'BAR', 'Bar', '🍷', { night: true, weekend: true }),
      S('Transportation', 4121, 7, 27, 'TAX', 'Taxi', '🚕', { weekend: true }),
      S('Transportation', 5541, 3, 72, 'FUE', 'Fuel station', '⛽'),
      S('Entertainment', 7922, 2, 64, 'ENT', 'Concert venue', '🎟️', { weekend: true }),
      S('Lifestyle', 5651, 3, 95, 'LIF', 'Clothing store', '🧥'),
      S('Travel', 4511, 0.5, 420, 'TRV', 'Airline', '✈️'),
      S('Travel', 7011, 0.5, 260, 'TRV', 'Hotel', '🏨'),
      S('Home & Tech', 5732, 0.8, 140, 'TEC', 'Electronics store', '📱'),
      S('Health', 8021, 0.3, 95, 'HEA', 'Dentist', '🦷'),
    ],
    finalBalance: 8432.19,
    goals: [
      { id: 'g-mika-1', name: 'Emergency fund', emoji: '🛟', kind: 'emergency', target_amount: 10000, saved_amount: 6200, deadline: '2027-03-31' },
      { id: 'g-mika-2', name: 'Electric car', emoji: '🚗', kind: 'car', target_amount: 15000, saved_amount: 4100, deadline: '2027-12-31' },
    ],
  },
  CUST00961: {
    customer: { customer_id: 'CUST00961', name: 'Sanna', age: 41, postal_code: '40100', tagline: 'Mortgage was rejected — building a path to a home', avatar_emoji: '🏡' },
    archetype: 'steady_planner',
    payday: 20,
    salary: 3380,
    rent: 1150,
    electricity: 68,
    phone: 34.9,
    streaming: [12.99],
    transit: 0,
    saving: 150,
    groceriesPerWeek: 2.8,
    groceryAvg: 54,
    spends: [
      S('Restaurants', 5812, 3, 38, 'RES', 'Restaurant', '🍽️', { weekend: true }),
      S('Restaurants', 5814, 6, 9, 'RES', 'Café', '☕'),
      S('Transportation', 5542, 4, 61, 'FUE', 'Fuel station', '⛽'),
      S('Health', 5912, 1.5, 24, 'PHA', 'Pharmacy', '💊'),
      S('Health', 8011, 0.4, 85, 'HEA', 'Doctor', '🩺'),
      S('Lifestyle', 5945, 1.5, 32, 'LIF', 'Toy store', '🧸'),
      S('Entertainment', 7996, 0.8, 55, 'ENT', 'Amusement park', '🎡', { weekend: true }),
      S('Home & Tech', 5200, 0.6, 120, 'HOM', 'Hardware store', '🔨'),
    ],
    finalBalance: 2918.55,
    goals: [
      { id: 'g-sanna-1', name: 'Home down payment', emoji: '🏡', kind: 'home', target_amount: 28000, saved_amount: 11400, deadline: '2028-06-30' },
      { id: 'g-sanna-2', name: 'Emergency fund', emoji: '🛟', kind: 'emergency', target_amount: 5000, saved_amount: 3100, deadline: '2027-01-31' },
    ],
  },
  CUST00001: {
    customer: { customer_id: 'CUST00001', name: 'Pirjo', age: 63, postal_code: '20100', tagline: 'Steady saver — how do I compare to my peers?', avatar_emoji: '🌻' },
    archetype: 'squirrel_saver',
    payday: 8,
    salary: 2610,
    rent: 690,
    electricity: 41,
    phone: 14.9,
    streaming: [9.99],
    transit: 30,
    saving: 500,
    groceriesPerWeek: 2.2,
    groceryAvg: 34,
    spends: [
      S('Restaurants', 5812, 2, 26, 'RES', 'Restaurant', '🍽️'),
      S('Restaurants', 5814, 4, 7.5, 'RES', 'Café', '☕'),
      S('Health', 5912, 2, 19, 'PHA', 'Pharmacy', '💊'),
      S('Health', 8099, 0.5, 70, 'HEA', 'Health clinic', '🩺'),
      S('Lifestyle', 5942, 1.5, 22, 'LIF', 'Bookstore', '📚'),
      S('Entertainment', 7922, 0.7, 48, 'ENT', 'Theatre', '🎭'),
      S('Travel', 4722, 0.25, 640, 'TRV', 'Travel agency', '🧳'),
    ],
    finalBalance: 14205.8,
    goals: [
      { id: 'g-pirjo-1', name: 'Grandkids trip', emoji: '🧳', kind: 'travel', target_amount: 3000, saved_amount: 2350, deadline: '2027-06-30' },
      { id: 'g-pirjo-2', name: 'Emergency fund', emoji: '🛟', kind: 'emergency', target_amount: 8000, saved_amount: 8000, deadline: null },
    ],
  },
  CUST05014: {
    customer: { customer_id: 'CUST05014', name: 'Joni', age: 23, postal_code: '00487', tagline: 'An unexpected repair led to a payday loan. Now aiming to get back in the black.', avatar_emoji: '🧰' },
    archetype: 'tightrope_walker',
    payday: 17,
    salary: 9100,
    rent: 2800,
    electricity: 120,
    phone: 45,
    streaming: [29.99, 15.99],
    transit: 60,
    gym: 49,
    saving: 0,
    groceriesPerWeek: 4.5,
    groceryAvg: 120,
    spends: [
      S('Restaurants', 5812, 34, 60, 'RES', 'Restaurant', '🍽️', { weekend: true }),
      S('Restaurants', 5814, 12, 11, 'RES', 'Café', '☕'),
      S('Restaurants', 5813, 4, 55, 'BAR', 'Bar', '🍸', { night: true, weekend: true }),
      S('Groceries', 5499, 8, 9, 'KIO', 'Kiosk', '🏪'),
      S('Transportation', 4121, 10, 32, 'TAX', 'Taxi', '🚕', { night: true, weekend: true }),
      S('Entertainment', 7999, 4, 40, 'ENT', 'Gaming', '🎮'),
      S('Lifestyle', 5651, 6, 160, 'LIF', 'Clothing store', '👕'),
      S('Lifestyle', 5999, 4, 55, 'LIF', 'Shop', '🛍️'),
      S('Health', 5912, 2, 30, 'PHA', 'Pharmacy', '💊'),
      S('Travel', 4511, 0.6, 700, 'TRV', 'Airline', '✈️'),
      S('Travel', 7011, 0.6, 450, 'TRV', 'Hotel', '🏨'),
      S('Home & Tech', 5200, 1, 450, 'HOM', 'Hardware store', '🔨'),
      S('Home & Tech', 5732, 0.5, 220, 'TEC', 'Electronics store', '📱'),
    ],
    finalBalance: -784.58,
    goals: [
      { id: 'g-joni-1', name: 'Back in the black', emoji: '🎯', kind: 'other', target_amount: 784.58, saved_amount: 0, deadline: '2027-09-18' },
    ],
  },
};

const DEFAULT_ID = 'CUST05020';
const cfgFor = (id: string): ProfileCfg => PROFILES[id] ?? PROFILES[DEFAULT_ID];

export const fixtureDemoCustomers = (locale: Locale = 'en'): DemoCustomer[] =>
  Object.values(PROFILES).map((p) => {
    const pair = DEMO_TAGLINE_L10N[p.customer.customer_id];
    return pair ? { ...p.customer, tagline: locale === 'fi' ? pair[0] : locale === 'sv' ? pair[1] : p.customer.tagline } : p.customer;
  });

//: Demo taglines that differ from the English label in PROFILES; the older five stay English.
const DEMO_TAGLINE_L10N: Record<string, [string, string]> = {
  CUST05014: [
    'Yllättävä remontti johti pikavippiin. Nyt tavoitteena on päästä takaisin plussalle.',
    'En oväntad reparation ledde till ett snabblån. Nu är målet att komma tillbaka på plus.',
  ],
};

// ───────────────────────── basket classification (SPEC §2, simplified) ─────────────────────────

function classify(cat: string, mcc: number | null, amount: number, recurring: boolean): Basket {
  if (amount > 0) return 'income';
  if (cat === 'Invest Deposit' || cat === 'Salary Sweep') return 'saving';
  if (recurring || cat === 'Housing' || cat === 'Utilities') return 'fixed';
  const abs = Math.abs(amount);
  if (cat === 'Groceries') return mcc === 5499 ? 'leak' : 'fixed';
  if (cat === 'Transportation') {
    if (mcc === 4111) return 'fixed';
    if ((mcc === 5541 || mcc === 5542 || mcc === 7523) && abs > 80) return 'irregular';
    return mcc === 4121 ? 'leak' : 'irregular';
  }
  if (cat === 'Health') return 'irregular';
  if (cat === 'Home & Tech') return mcc === 5200 || mcc === 5251 || abs > 150 ? 'irregular' : 'leak';
  return 'leak';
}

const MCC_LABEL: Record<number, string> = {
  5411: 'Grocery store', 5499: 'Convenience store', 5812: 'Restaurant', 5814: 'Fast food / café', 5813: 'Bar',
  4121: 'Taxi', 4111: 'Public transit', 5541: 'Fuel', 5542: 'Fuel (automated)', 7832: 'Cinema', 7999: 'Recreation',
  7922: 'Theatre & concerts', 7996: 'Amusement park', 7991: 'Gym & sports', 5651: 'Clothing', 5999: 'Retail', 5941: 'Sporting goods',
  5942: 'Books', 5945: 'Toys', 5912: 'Pharmacy', 8011: 'Doctor', 8099: 'Health services', 8021: 'Dentist', 5732: 'Electronics',
  5200: 'Home supply', 4511: 'Airline', 7011: 'Hotel', 4722: 'Travel agency',
};

// ───────────────────────── transaction generator ─────────────────────────

type Gen = { txs: Tx[]; recurring: RecurringItem[] };
const cache = new Map<string, Gen>();

function generate(id: string): Gen {
  const hit = cache.get(id);
  if (hit) return hit;
  const p = cfgFor(id);
  const rnd = mulberry32(hashSeed(id));
  const raw: Omit<Tx, 'balance_after' | 'id'>[] = [];
  const recurring: RecurringItem[] = [];

  const push = (date: string, hour: number, amount: number, category: string, type: string, mcc: number | null, prefix: string, num: number, label: string, icon: string, isRecurring = false) => {
    const minute = Math.floor(rnd() * 60);
    raw.push({
      date,
      timestamp: `${date}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:00`,
      amount: r2(amount),
      category,
      basket: classify(category, mcc, amount, isRecurring),
      merchant_id: prefix ? `MRC-${prefix}-${String(num).padStart(4, '0')}` : null,
      merchant_label: label,
      mcc,
      mcc_label: mcc ? (MCC_LABEL[mcc] ?? null) : null,
      icon,
      type,
    });
  };

  const addRecurring = (label: string, category: string, prefix: string, num: number, amount: number, day: number, basket: Basket = 'fixed') => {
    recurring.push({ label, category, merchant_id: `MRC-${prefix}-${String(num).padStart(4, '0')}`, avg_amount: amount, cadence: 'monthly', day_of_month: day, last_date: '', basket });
  };

  addRecurring('Rent', 'Housing', 'HOU', 7, p.rent, 1);
  addRecurring('Electricity #3', 'Utilities', 'UTL', 3, p.electricity, 6);
  addRecurring('Mobile plan #4', 'Utilities', 'TEL', 4, p.phone, 10);
  p.streaming.forEach((amt, i) => addRecurring(`Streaming #${i + 2}`, 'Entertainment', 'STR', i + 2, amt, 12 + i * 4));
  if (p.transit) addRecurring('Public transit #1', 'Transportation', 'TRN', 1, p.transit, 2);
  if (p.gym) addRecurring('Gym #2', 'Entertainment', 'GYM', 2, p.gym, 4);

  for (let d = HISTORY_START; d <= AS_OF; d = addDays(d, 1)) {
    const dt = toDate(d);
    const dom = dt.getUTCDate();
    const dow = dt.getUTCDay();
    const weekend = dow === 0 || dow === 5 || dow === 6;

    if (dom === p.payday) {
      push(d, 6, p.salary * (0.98 + rnd() * 0.04), 'Salary', 'salary', null, '', 0, 'Salary', '💼');
      if (p.saving) push(d, 7, -p.saving, 'Salary Sweep', 'salary_sweep', null, '', 0, 'Savings sweep', '🐷');
    }
    if (p.otherIncome && dom === p.otherIncome.day) push(d, 8, p.otherIncome.amount, 'Other Income', 'other_income', null, '', 0, 'Study grant', '🎓');

    for (const rec of recurring) {
      if (rec.day_of_month === dom) {
        const amount = rec.category === 'Utilities' && rec.label.startsWith('Electricity') ? rec.avg_amount * (0.8 + rnd() * 0.4) : rec.avg_amount;
        const type = rec.category === 'Housing' ? 'housing_payment' : rec.category === 'Utilities' ? 'utilities_payment' : 'purchase';
        const mcc = rec.category === 'Transportation' ? 4111 : rec.category === 'Entertainment' ? 7991 : null;
        const num = Number(rec.merchant_id?.slice(-4) ?? 0);
        push(d, 9, -amount, rec.category, type, mcc, rec.merchant_id?.slice(4, 7) ?? '', num, rec.label, rec.category === 'Housing' ? '🏠' : rec.category === 'Utilities' ? '💡' : rec.category === 'Transportation' ? '🚌' : '📺', true);
        rec.last_date = d;
      }
    }

    // Groceries: Poisson-ish per day from weekly rate.
    if (rnd() < p.groceriesPerWeek / 7) {
      const num = 1 + Math.floor(rnd() * 3) * 17;
      push(d, 16 + Math.floor(rnd() * 4), -p.groceryAvg * (0.5 + rnd()), 'Groceries', 'purchase', 5411, 'GRO', num + 18, `Grocery store #${num + 18}`, '🛒');
    }
    for (const s of p.spends) {
      let rate = s.perMonth / 30;
      if (s.weekend) rate *= weekend ? 1.9 : 0.55;
      if (rnd() < rate) {
        const num = 1 + Math.floor(rnd() * 4) * 7;
        const hour = s.night ? (rnd() < 0.6 ? 22 + Math.floor(rnd() * 2) : 1 + Math.floor(rnd() * 2)) : 10 + Math.floor(rnd() * 9);
        const amount = s.avg * (1 - s.spread + rnd() * s.spread * 2);
        push(d, hour, -amount, s.cat, 'purchase', s.mcc, s.prefix, num, `${s.label} #${num}`, s.icon);
      }
    }
  }

  raw.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  // Balances are computed backwards from a chosen final balance so each persona's
  // story (e.g. Leo hovering near zero) holds exactly on the AS_OF date.
  let bal = p.finalBalance;
  const txs: Tx[] = new Array(raw.length);
  for (let i = raw.length - 1; i >= 0; i--) {
    txs[i] = { ...raw[i], id: `${id}-${i}`, balance_after: r2(bal) };
    bal -= raw[i].amount;
  }
  const out = { txs, recurring };
  cache.set(id, out);
  return out;
}

// ───────────────────────── analytics over fixtures ─────────────────────────

const isSpend = (t: Tx) => t.amount < 0 && t.basket !== 'saving';
const sumAbs = (xs: Tx[]) => r2(xs.reduce((a, t) => a + Math.abs(t.amount), 0));

/** Average monthly value over the last `n` full months before AS_OF. */
function monthlyAvg(txs: Tx[], pred: (t: Tx) => boolean, n = 3): number {
  const end = monthStart(AS_OF);
  const start = addMonths(end, -n);
  return r2(sumAbs(txs.filter((t) => t.date >= start && t.date < end && pred(t))) / n);
}

function filterTx(txs: Tx[], q: TransactionQuery & SpendingQuery): Tx[] {
  const text = q.text?.toLowerCase();
  return txs.filter(
    (t) =>
      (!q.start || t.date >= q.start) &&
      (!q.end || t.date <= q.end) &&
      (!q.category || t.category === q.category) &&
      (!q.basket || t.basket === q.basket) &&
      (!q.merchant || t.merchant_id === q.merchant || t.merchant_label === q.merchant) &&
      (!text || `${t.merchant_label} ${t.category} ${t.mcc_label ?? ''}`.toLowerCase().includes(text)),
  );
}

export function fixtureTransactions(id: string, q: TransactionQuery = {}): TransactionsResult {
  const all = filterTx(generate(id).txs, q).slice().reverse();
  const offset = q.offset ?? 0;
  return { items: all.slice(offset, offset + (q.limit ?? 50)), total_count: all.length };
}

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function fixtureSpending(id: string, q: SpendingQuery = {}): SpendingResult {
  const start = q.start ?? addMonths(AS_OF, -1);
  const end = q.end ?? AS_OF;
  const rows = filterTx(generate(id).txs, { ...q, start, end }).filter(isSpend);
  const total = sumAbs(rows);
  const groupBy = q.group_by ?? 'none';
  const map = new Map<string, { label: string; total: number; count: number }>();
  if (groupBy !== 'none') {
    for (const t of rows) {
      let key: string;
      let label: string;
      switch (groupBy) {
        case 'category': key = label = t.category; break;
        case 'basket': key = label = t.basket; break;
        case 'month': key = label = monthKey(t.date); break;
        case 'week': key = label = addDays(t.date, -((toDate(t.date).getUTCDay() + 6) % 7)); break;
        case 'weekday': { const w = toDate(t.date).getUTCDay(); key = String(w); label = WEEKDAYS[w]; break; }
        case 'merchant': key = t.merchant_id ?? t.merchant_label; label = t.merchant_label; break;
        case 'hour': key = label = t.timestamp.slice(11, 13); break;
        default: key = label = t.date;
      }
      const g = map.get(key) ?? { label, total: 0, count: 0 };
      g.total += Math.abs(t.amount);
      g.count += 1;
      map.set(key, g);
    }
  }
  const groups = [...map.entries()].map(([key, g]) => ({ key, label: g.label, total: r2(g.total), count: g.count }));
  const chronological = groupBy === 'month' || groupBy === 'week' || groupBy === 'day' || groupBy === 'hour' || groupBy === 'weekday';
  groups.sort((a, b) => (chronological ? a.key.localeCompare(b.key) : b.total - a.total));
  return {
    filters: { ...q },
    total,
    count: rows.length,
    avg_tx: rows.length ? r2(total / rows.length) : 0,
    groups: chronological ? groups : groups.slice(0, 20),
    period: { start, end },
  };
}

const EXPLAIN: Record<Locale, Record<BasketKey, string>> = {
  en: {
    fixed: 'Must-pay, every month: rent, utilities, groceries, transit pass and subscriptions. Predictable — plan it first.',
    irregular: 'Must-pay, but not monthly: health, car, repairs. They feel like surprises unless you set money aside.',
    leak: 'Everyday choices that slip through your fingers: cafés, takeaway, taxis, shopping. Your easiest lever.',
  },
  fi: {
    fixed: 'Pakolliset, joka kuukausi: vuokra, sähkö, ruoka, matkakortti ja tilaukset. Ennustettavia — suunnittele nämä ensin.',
    irregular: 'Pakolliset, mutta epäsäännölliset: terveys, auto, korjaukset. Ne yllättävät, ellei niihin varaudu.',
    leak: 'Arjen valinnat, jotka valuvat sormien läpi: kahvilat, noutoruoka, taksit, shoppailu. Helpoin vipusi.',
  },
  sv: {
    fixed: 'Måste betalas varje månad: hyra, el, mat, månadskort och prenumerationer. Förutsägbara – planera dem först.',
    irregular: 'Måste betalas, men inte varje månad: hälsa, bil, reparationer. De känns som överraskningar om du inte lägger undan pengar.',
    leak: 'Vardagsval som rinner mellan fingrarna: kaféer, hämtmat, taxi, shopping. Din lättaste spak.',
  },
};

export function fixtureBaskets(id: string, months = 6, locale: Locale = 'en'): BasketsResult {
  const txs = generate(id).txs;
  const keys: string[] = [];
  for (let i = months - 1; i >= 0; i--) keys.push(monthKey(addMonths(monthStart(AS_OF), -i)));
  const rows = keys.map((m) => {
    const inMonth = txs.filter((t) => monthKey(t.date) === m);
    const s = (b: Basket) => sumAbs(inMonth.filter((t) => t.basket === b));
    return { month: m, fixed: s('fixed'), irregular: s('irregular'), leak: s('leak'), income: s('income'), saving: s('saving') };
  });
  const cur = rows[rows.length - 1];
  const inCur = txs.filter((t) => monthKey(t.date) === cur.month);
  const top = (b: BasketKey) => {
    const m = new Map<string, number>();
    for (const t of inCur.filter((x) => x.basket === b)) {
      const label = t.basket === 'fixed' && t.category !== 'Groceries' ? t.merchant_label : (t.mcc_label ?? t.category);
      m.set(label, (m.get(label) ?? 0) + Math.abs(t.amount));
    }
    return [...m.entries()].map(([label, total]) => ({ label, total: r2(total) })).sort((a, b) => b.total - a.total).slice(0, 4);
  };
  return {
    months: rows,
    current_month: { ...cur, top: { fixed: top('fixed'), irregular: top('irregular'), leak: top('leak') } },
    explanations: EXPLAIN[locale],
  };
}

export function fixtureRecurring(id: string): RecurringResult {
  const { recurring } = generate(id);
  const items = recurring.map((r) => ({ ...r, avg_amount: r2(r.avg_amount) }));
  return { items, monthly_total: r2(items.reduce((a, r) => a + r.avg_amount, 0)) };
}

// ── goals (in-memory, seeded) ──
const goalStore = new Map<string, Goal[]>();

function withProgress(g: Omit<Goal, 'progress' | 'created_at' | 'monthly_contribution'> & Partial<Goal>): Goal {
  const months = g.deadline ? Math.max(1, Math.round(diffDays(AS_OF, g.deadline) / 30.4)) : 12;
  const left = Math.max(0, g.target_amount - g.saved_amount);
  return {
    created_at: g.created_at ?? '2026-05-02T10:00:00',
    ...g,
    monthly_contribution: g.monthly_contribution ?? r2(left / months),
    progress: g.target_amount > 0 ? Math.min(1, g.saved_amount / g.target_amount) : 0,
  };
}

export function fixtureGoals(id: string, locale: Locale = 'en'): Goal[] {
  return goalStoreFor(id).map((g) => {
    const pair = SEED_GOAL_NAME_L10N[g.name];
    return pair ? { ...g, name: locale === 'fi' ? pair[0] : locale === 'sv' ? pair[1] : g.name } : g;
  });
}

//: Seeded goal names as stored in English; a user-typed name is not in this map and stays as typed.
const SEED_GOAL_NAME_L10N: Record<string, [string, string]> = {
  'Emergency fund': ['Puskurirahasto', 'Buffert'],
  'New laptop': ['Uusi läppäri', 'Ny dator'],
  'Summer trip': ['Kesämatka', 'Sommarresa'],
  'Electric car': ['Sähköauto', 'Elbil'],
  'Home down payment': ['Asunnon käsiraha', 'Egen insats för bostad'],
  'Trip with the grandkids': ['Matka lastenlasten kanssa', 'Resa med barnbarnen'],
  'Grandkids trip': ['Matka lastenlasten kanssa', 'Resa med barnbarnen'],
  'Payday buffer': ['Palkkapäiväpuskuri', 'Buffert till lönedagen'],
  'Interrail summer': ['Interrail-kesämatka', 'Interrail-sommarresa'],
  'Back in the black': ['Takaisin plussalle', 'Tillbaka på plus'],
};

function goalStoreFor(id: string): Goal[] {
  if (!goalStore.has(id)) goalStore.set(id, cfgFor(id).goals.map((g) => withProgress(g)));
  return goalStore.get(id)!;
}

const KIND_EMOJI: Record<GoalKind, string> = { car: '🚗', travel: '✈️', home: '🏡', emergency: '🛟', education: '🎓', gadget: '💻', other: '🎯' };

export function fixtureCreateGoal(id: string, body: GoalCreate): Goal {
  const kind = body.kind ?? 'other';
  const g = withProgress({
    id: `g-${Date.now().toString(36)}`,
    name: body.name,
    emoji: body.emoji ?? KIND_EMOJI[kind],
    kind,
    target_amount: body.target_amount,
    saved_amount: body.saved_amount ?? 0,
    deadline: body.deadline ?? null,
    created_at: new Date().toISOString(),
  });
  goalStore.set(id, [...goalStoreFor(id), g]);
  return g;
}

export function fixtureUpdateGoal(id: string, goalId: string, patch: GoalUpdate): Goal {
  const goals = goalStoreFor(id);
  const cur = goals.find((g) => g.id === goalId);
  if (!cur) throw new Error('Goal not found');
  const next = withProgress({ ...cur, ...patch, monthly_contribution: patch.monthly_contribution } as Goal);
  goalStore.set(id, goals.map((g) => (g.id === goalId ? next : g)));
  return next;
}

export function fixtureDeleteGoal(id: string, goalId: string): { deleted: boolean; id: string } {
  goalStore.set(id, goalStoreFor(id).filter((g) => g.id !== goalId));
  return { deleted: true, id: goalId };
}

function nextPayday(id: string): string {
  return nextDayOfMonth(AS_OF, cfgFor(id).payday);
}

function balanceOf(id: string): number {
  const txs = generate(id).txs.filter((t) => t.date <= AS_OF);
  return txs[txs.length - 1]?.balance_after ?? 0;
}

function upcomingBills(id: string, until: string) {
  return fixtureRecurring(id)
    .items.map((r) => ({ label: r.label, amount: r.avg_amount, expected_date: nextDayOfMonth(AS_OF, r.day_of_month ?? 1) }))
    .filter((b) => b.expected_date <= until)
    .sort((a, b) => a.expected_date.localeCompare(b.expected_date));
}

export function fixtureSafeToSpend(id: string, locale: Locale = 'en'): SafeToSpend {
  fmtLocale = locale;
  const txs = generate(id).txs;
  const balance = balanceOf(id);
  const payday = nextPayday(id);
  const days = Math.max(1, diffDays(AS_OF, payday));
  const bills = upcomingBills(id, payday);
  const billsTotal = r2(bills.reduce((a, b) => a + b.amount, 0));
  const irregularBuffer = r2((monthlyAvg(txs, (t) => t.basket === 'irregular') * days) / 30);
  const goalContrib = r2(fixtureGoals(id, locale).reduce((a, g) => a + (g.progress < 1 ? g.monthly_contribution : 0), 0) * Math.min(1, days / 30) * 0.5);
  const safeTotal = r2(Math.max(0, balance - billsTotal - irregularBuffer - goalContrib));
  const perDay = r2(safeTotal / days);
  const status: SafeToSpend['status'] = perDay >= 25 ? 'comfortable' : perDay >= 8 ? 'tight' : 'critical';
  const explanation = tr(
    locale,
    `Balance ${fmt(balance)} − upcoming bills ${fmt(billsTotal)} − irregular buffer ${fmt(irregularBuffer)} − goal savings ${fmt(goalContrib)} = ${fmt(safeTotal)} for the ${days} days until payday.`,
    `Saldo ${fmt(balance)} − tulevat laskut ${fmt(billsTotal)} − puskuri epäsäännöllisiin menoihin ${fmt(irregularBuffer)} − tavoitesäästöt ${fmt(goalContrib)} = ${fmt(safeTotal)} palkkapäivään asti (${days} päivää).`,
    `Saldo ${fmt(balance)} − kommande räkningar ${fmt(billsTotal)} − buffert för oregelbundna utgifter ${fmt(irregularBuffer)} − målsparande ${fmt(goalContrib)} = ${fmt(safeTotal)} för ${days} dagar fram till lönen.`,
  );
  return {
    balance,
    next_payday: payday,
    days_until_payday: days,
    upcoming_bills: bills,
    irregular_buffer: irregularBuffer,
    goal_contributions: goalContrib,
    safe_total: safeTotal,
    safe_per_day: perDay,
    safe_this_week: r2(perDay * Math.min(7, days)),
    status,
    explanation,
  };
}

const ARCHETYPES: Record<string, Record<Locale, [string, string]> & { emoji: string }> = {
  steady_planner: { emoji: '🧭', en: ['Steady Planner', 'Your money follows a rhythm: bills first, then life. Few surprises.'], fi: ['Vakaa suunnittelija', 'Rahasi kulkee rytmissä: ensin laskut, sitten elämä. Vähän yllätyksiä.'], sv: ['Stadig planerare', 'Dina pengar följer en rytm: räkningarna först, sedan livet. Få överraskningar.'] },
  weekend_treater: { emoji: '🎉', en: ['Weekend Treater', 'Weekdays are calm — then Friday to Sunday the leaks open up.'], fi: ['Viikonlopun herkuttelija', 'Arki on rauhallista – perjantaista sunnuntaihin rahaa alkaa vuotaa.'], sv: ['Helgunnare', 'Vardagarna är lugna – sedan, från fredag till söndag, börjar pengarna läcka.'] },
  latte_leaker: { emoji: '☕', en: ['Latte Leaker', 'Lots of small, frequent purchases that quietly add up to a big number.'], fi: ['Lattevuotaja', 'Paljon pieniä, toistuvia ostoksia, jotka kasvavat huomaamatta isoksi summaksi.'], sv: ['Lattespenderare', 'Många små, täta köp som i det tysta blir en stor summa.'] },
  impulse_splurger: { emoji: '⚡', en: ['Impulse Splurger', 'Occasional big unplanned purchases make your months swing.'], fi: ['Heräteostaja', 'Satunnaiset isot suunnittelemattomat ostot heiluttavat kuukausiasi.'], sv: ['Impulsköpare', 'Enstaka stora, oplanerade köp får dina månader att svänga.'] },
  squirrel_saver: { emoji: '🐿️', en: ['Squirrel Saver', 'You put money away first and spend what is left. Classic saver.'], fi: ['Oravasäästäjä', 'Säästät ensin ja käytät sen, mitä jää. Klassinen säästäjä.'], sv: ['Ekorrsparare', 'Du sparar först och använder det som blir kvar. En klassisk sparare.'] },
  tightrope_walker: { emoji: '🎪', en: ['Tightrope Walker', 'Your balance runs close to zero before payday — little room for surprises.'], fi: ['Nuorallatanssija', 'Saldosi käy lähellä nollaa ennen palkkapäivää – yllätyksille jää vähän tilaa.'], sv: ['Lindansare', 'Ditt saldo ligger nära noll före lönen – lite utrymme för överraskningar.'] },
};

export function fixtureProfile(id: string, locale: Locale = 'en'): SpenderProfile {
  const p = cfgFor(id);
  const txs = generate(id).txs.filter((t) => t.date >= addMonths(monthStart(AS_OF), -3) && t.date < monthStart(AS_OF));
  const spend = txs.filter(isSpend);
  const total = sumAbs(spend) || 1;
  const income = sumAbs(txs.filter((t) => t.basket === 'income')) || 1;
  const saving = sumAbs(txs.filter((t) => t.basket === 'saving'));
  const leak = sumAbs(spend.filter((t) => t.basket === 'leak'));
  const weekend = sumAbs(spend.filter((t) => [0, 5, 6].includes(toDate(t.date).getUTCDay())));
  const small = spend.filter((t) => Math.abs(t.amount) < 15).length / 13;
  const late = spend.filter((t) => { const h = Number(t.timestamp.slice(11, 13)); return h >= 22 || h < 5; }).length / Math.max(1, spend.length);
  const savingsRate = r2((income - total) / income + saving / income);
  const a = ARCHETYPES[p.archetype];
  const [name, description] = a[locale];
  const pct = (x: number) => Math.round(Math.max(0, Math.min(1, x)) * 100);
  const T = (en: string, fi: string, sv: string) => tr(locale, en, fi, sv);
  const P = (x: number) => (locale === 'en' ? `${Math.round(x * 100)}%` : `${Math.round(x * 100)}\u00A0%`);
  const perWeek = locale === 'en' ? small.toFixed(1) : small.toFixed(1).replace('.', ',');
  return {
    archetype: { key: p.archetype, name, emoji: a.emoji, description },
    traits: [
      { key: 'saver', label: T('Saving', 'Säästäminen', 'Sparande'), score: pct(savingsRate / 0.25), detail: T(`${P(savingsRate)} of income kept`, `${P(savingsRate)} tuloista jää säästöön`, `${P(savingsRate)} av inkomsten blir kvar`) },
      { key: 'leaks', label: T('Leaks', 'Vuodot', 'Läckor'), score: pct(leak / total / 0.5), detail: T(`${P(leak / total)} of spending is leaks`, `${P(leak / total)} kulutuksesta on vuotoja`, `${P(leak / total)} av utgifterna är läckor`) },
      { key: 'weekend', label: T('Weekend', 'Viikonloppu', 'Helger'), score: pct(weekend / total / 0.6), detail: T(`${P(weekend / total)} Fri–Sun`, `${P(weekend / total)} pe–su`, `${P(weekend / total)} fre–sön`) },
      { key: 'small', label: T('Small buys', 'Pikkuostot', 'Småköp'), score: pct(small / 15), detail: T(`${perWeek} buys under €15 / week`, `${perWeek} alle 15 € ostosta / vko`, `${perWeek} köp under 15 € / vecka`) },
      { key: 'night', label: T('Late night', 'Yöostot', 'Sena kvällar'), score: pct(late / 0.25), detail: T(`${P(late)} between 22–05`, `${P(late)} klo 22–05`, `${P(late)} kl. 22–05`) },
    ],
    savings_rate: savingsRate,
    leak_share: r2(leak / total),
    weekend_share: r2(weekend / total),
    small_tx_per_week: r2(small),
    late_night_share: r2(late),
    volatility: r2(p.archetype === 'tightrope_walker' ? 0.42 : p.archetype === 'squirrel_saver' ? 0.08 : 0.21),
  };
}

const STAT_FI: Record<string, number> = { Groceries: 285, Restaurants: 92, Transportation: 165, Entertainment: 68, Lifestyle: 84, Utilities: 88, Health: 55 };
const PEER_FACTOR: Record<string, Record<string, number>> = {
  CUST05020: { Restaurants: 0.62, Lifestyle: 0.8, Groceries: 1.05, Transportation: 1.2, Entertainment: 0.9, Utilities: 1.1, Health: 1 },
  CUST00584: { Restaurants: 0.7, Lifestyle: 1.1, Groceries: 1.2, Transportation: 0.75, Entertainment: 0.8, Utilities: 0.95, Health: 1.2 },
  CUST00586: { Restaurants: 0.55, Lifestyle: 0.7, Groceries: 1, Transportation: 0.6, Entertainment: 0.75, Utilities: 1, Health: 1.1 },
  CUST00961: { Restaurants: 1.1, Lifestyle: 1.05, Groceries: 0.95, Transportation: 1, Entertainment: 1.1, Utilities: 1.05, Health: 0.9 },
  CUST00001: { Restaurants: 1.4, Lifestyle: 1.2, Groceries: 1.1, Transportation: 1.1, Entertainment: 1.15, Utilities: 1.1, Health: 1.1 },
};

export function fixtureBenchmarks(id: string): Benchmarks {
  const p = cfgFor(id);
  const txs = generate(id).txs;
  const age = p.customer.age;
  const band = age < 26 ? '18-25' : age < 36 ? '26-35' : age < 51 ? '36-50' : age < 65 ? '51-64' : '65+';
  const categories = Object.keys(STAT_FI).map((cat) => {
    const you = monthlyAvg(txs, (t) => isSpend(t) && t.category === cat);
    const median = r2(Math.max(5, you * (PEER_FACTOR[p.customer.customer_id]?.[cat] ?? 1)));
    const z = (you - median) / (median * 0.45);
    const percentile = Math.round(100 / (1 + Math.exp(-1.7 * z)));
    return { category: cat, you_monthly: you, peer_median_monthly: median, peer_p25: r2(median * 0.62), peer_p75: r2(median * 1.45), percentile, stat_fi_monthly: STAT_FI[cat] };
  });
  return {
    peer_group: { label: `Age ${band} in dataset`, size: 412 + (hashSeed(band) % 600) },
    categories,
    sources: [
      { name: 'Statistics Finland — Household budget survey', url: 'https://stat.fi/en/statistics/kot', note: 'Per-person monthly averages, rounded (demo approximation).' },
      { name: 'Junction 2026 synthetic dataset', url: 'https://www.s-pankki.fi', note: 'Peer medians computed from 5 100 synthetic customers.' },
    ],
  };
}

export function fixtureWhatIf(id: string, req: WhatIfRequest): WhatIfResult {
  const txs = generate(id).txs;
  const horizon = req.horizon_months ?? 12;
  const monthlyReturn = (req.invest_return_pct ?? 0) / 100 / 12;
  const perItem = req.adjustments.map((a) => {
    const baseline = monthlyAvg(txs, (t) => isSpend(t) && (!a.category || t.category === a.category) && (!a.basket || t.basket === a.basket) && (!a.merchant || t.merchant_id === a.merchant));
    const next = r2(baseline * (1 + a.change_pct / 100));
    return { label: a.category ?? a.basket ?? a.merchant ?? 'spending', baseline_monthly: baseline, new_monthly: next, monthly_saving: r2(baseline - next) };
  });
  const baseline = r2(perItem.reduce((s, x) => s + x.baseline_monthly, 0));
  const next = r2(perItem.reduce((s, x) => s + x.new_monthly, 0));
  const monthly = r2(baseline - next);
  const series: { month: number; cumulative: number }[] = [];
  let cum = 0;
  for (let m = 1; m <= horizon; m++) {
    cum = cum * (1 + monthlyReturn) + monthly;
    series.push({ month: m, cumulative: r2(cum) });
  }
  return { baseline_monthly: baseline, new_monthly: next, monthly_saving: monthly, horizon_months: horizon, total_saving: r2(monthly * horizon), with_return: r2(cum), per_item: perItem, series };
}

const CUT_PCT: Record<string, number> = { Restaurants: 30, Transportation: 50, Entertainment: 25, Lifestyle: 30, Groceries: 40, Travel: 20, 'Home & Tech': 30 };

function monthlySurplus(id: string): number {
  const txs = generate(id).txs;
  const income = monthlyAvg(txs, (t) => t.basket === 'income');
  const out = monthlyAvg(txs, (t) => t.amount < 0);
  return r2(income - out); // negative when spending exceeds income: the deficit widens the gap
}

/**
 * Same recovery rules as the backend (`backend/app/analytics/recovery.py`), on the demo
 * history's own numbers: negative balance wins, then a negative six-month cashflow.
 * Safe-to-spend urgency stays separate, and goal contributions can make it tight.
 */
export function fixtureRecovery(id: string, locale: Locale = 'en'): Recovery {
  const txs = generate(id).txs;
  const months = 6;
  const end = monthStart(AS_OF);
  const start = addMonths(end, -months);
  const window = txs.filter((t) => t.date >= start && t.date < end);
  const income = r2(sumAbs(window.filter((t) => t.basket === 'income')) / months);
  const spending = r2(sumAbs(window.filter(isSpend)) / months);
  const surplus = r2(income - spending);
  const balance = balanceOf(id);
  const known = window.length > 0 && Number.isFinite(balance) && Number.isFinite(surplus);
  const cents = (v: number) => Math.round(v * 100);
  const state: Recovery['state'] = !known
    ? 'unknown'
    : cents(balance) < 0
      ? 'balance_repair'
      : cents(surplus) < 0
        ? 'cashflow_stabilizing'
        : 'ordinary';
  const goals = fixtureGoals(id, locale).filter((g) => g.progress < 1);
  const goalNeed = r2(goals.reduce((a, g) => a + (g.monthly_contribution || 0), 0));
  const deficit = state === 'unknown' ? 0 : r2(Math.max(0, -surplus));
  const sts = fixtureSafeToSpend(id, locale);
  return {
    state,
    months,
    balance: Number.isFinite(balance) ? balance : null,
    monthly_income: Number.isFinite(income) ? income : null,
    monthly_spending: Number.isFinite(spending) ? spending : null,
    monthly_surplus: Number.isFinite(surplus) ? surplus : null,
    deficit: known ? deficit : null,
    goal_monthly_need: goalNeed,
    planned_monthly_change: deficit > 0 ? r2(deficit + goalNeed) : null,
    urgency: known ? sts.status : null,
    safe_per_day: known ? sts.safe_per_day : null,
    days_until_payday: sts.days_until_payday,
    goal_contributions: sts.goal_contributions,
    goal_reservations_present: sts.goal_contributions > 0,
    tx_count: window.length,
    period: `${start}..${addDays(end, -1)}`,
  };
}

export function fixturePlanGoal(id: string, req: GoalPlanRequest, locale: Locale = 'en'): GoalPlan {
  fmtLocale = locale;
  const txs = generate(id).txs;
  const saved = req.saved_amount ?? 0;
  const deadline = req.deadline ?? addMonths(AS_OF, 12);
  const months = Math.max(1, Math.round(diffDays(AS_OF, deadline) / 30.4));
  const needed = r2(Math.max(0, req.target_amount - saved) / months);
  const surplus = monthlySurplus(id);
  const gap = r2(Math.max(0, needed - surplus));
  const leakByCat = new Map<string, number>();
  for (const cat of Object.keys(CUT_PCT)) {
    const v = monthlyAvg(txs, (t) => t.basket === 'leak' && t.category === cat);
    if (v > 5) leakByCat.set(cat, v);
  }
  const WHY: Record<string, [string, string, string]> = {
    Restaurants: ['Cook 2 more meals a week at home', 'Kokkaa kotona kaksi ateriaa enemmän viikossa', 'Laga två måltider till hemma varje vecka'],
    Transportation: ['Swap half of taxi rides for transit or a bike', 'Vaihda puolet taksimatkoista joukkoliikenteeseen tai pyörään', 'Byt hälften av taxiresorna mot kollektivtrafik eller cykel'],
    Entertainment: ['Pick your favourite subscriptions, pause the rest', 'Pidä suosikkitilaukset, tauota muut', 'Behåll favoritprenumerationerna, pausa resten'],
    Lifestyle: ['48-hour rule before non-essential shopping', '48 tunnin sääntö ennen muita kuin välttämättömiä ostoksia', '48-timmarsregeln före köp du inte behöver'],
    Groceries: ['Fewer kiosk stops — plan one weekly shop', 'Vähemmän kioskikäyntejä – yksi suunniteltu viikko-ostos', 'Färre kioskbesök – planera ett veckoköp'],
    Travel: ['Book off-season or a bit earlier', 'Varaa sesongin ulkopuolella tai vähän aiemmin', 'Boka utanför säsong eller lite tidigare'],
    'Home & Tech': ['Wait for a sale or buy refurbished', 'Odota alennusta tai osta kunnostettu', 'Vänta på rea eller köp renoverat'],
  };
  const cuts: GoalPlan['cuts'] = [];
  let covered = 0;
  for (const [cat, cur] of [...leakByCat.entries()].sort((a, b) => b[1] - a[1])) {
    if (covered >= gap && gap > 0) break;
    if (gap === 0 && cuts.length >= 2) break;
    const pct = CUT_PCT[cat];
    const saving = r2((cur * pct) / 100);
    cuts.push({ label: cat, category: cat, basket: 'leak', current_monthly: cur, cut_pct: pct, monthly_saving: saving, why: WHY[cat]?.[locale === 'fi' ? 1 : locale === 'sv' ? 2 : 0] ?? '' });
    covered += saving;
  }
  const cutsTotal = r2(cuts.reduce((a, c) => a + c.monthly_saving, 0));
  const feasibility: GoalPlan['feasibility'] = gap <= 0 ? 'on_track' : cutsTotal >= gap ? 'stretch' : 'unrealistic';
  const capacity = surplus + cutsTotal;
  const suggestedMonths = capacity > 0 ? Math.ceil(Math.max(0, req.target_amount - saved) / capacity) : null;
  const suggested = feasibility === 'unrealistic' && suggestedMonths ? addMonths(AS_OF, suggestedMonths) : null;
  const summary =
    feasibility === 'on_track'
      ? tr(locale, `You need ${fmt(needed)}/month and your current surplus is ${fmt(surplus)} — you're on track.`, `Tarvitset ${fmt(needed)}/kk, ja nykyinen ylijäämäsi on ${fmt(surplus)} – olet aikataulussa.`, `Du behöver ${fmt(needed)}/mån och ditt nuvarande överskott är ${fmt(surplus)} – du ligger i fas.`)
      : feasibility === 'stretch'
        ? tr(locale, `You need ${fmt(needed)}/month. Surplus ${fmt(surplus)} plus leak-basket cuts of ${fmt(cutsTotal)} close the gap.`, `Tarvitset ${fmt(needed)}/kk. Ylijäämä ${fmt(surplus)} ja vuotokorin leikkaukset ${fmt(cutsTotal)} riittävät.`, `Du behöver ${fmt(needed)}/mån. Överskottet ${fmt(surplus)} plus nedskärningar i läckkorgen på ${fmt(cutsTotal)} räcker.`)
        : capacity <= 0
          ? tr(locale, `You need ${fmt(needed)}/month, but you spend more than you earn. Close the ${fmt(-surplus)}/month deficit first, plus ${fmt(needed)}/month for the goal — ${fmt(-surplus + needed)}/month in total.`, `Tarvitset ${fmt(needed)}/kk, mutta kulutat enemmän kuin tienaat. Kuro ensin ${fmt(-surplus)}/kk vaje umpeen ja varaa lisäksi ${fmt(needed)}/kk tavoitteelle – yhteensä ${fmt(-surplus + needed)}/kk.`, `Du behöver ${fmt(needed)}/mån, men du spenderar mer än du tjänar. Täpp först underskottet på ${fmt(-surplus)}/mån och lägg ${fmt(needed)}/mån för målet – ${fmt(-surplus + needed)}/mån totalt.`)
          : tr(locale, `You need ${fmt(needed)}/month but a realistic pace is ${fmt(capacity)}/month. Move the deadline.`, `Tarvitset ${fmt(needed)}/kk, mutta realistinen tahti on ${fmt(capacity)}/kk. Siirrä tavoitepäivää.`, `Du behöver ${fmt(needed)}/mån, men en realistisk takt är ${fmt(capacity)}/mån. Flytta fram måldatumet.`);
  return { name: req.name ?? null, target_amount: req.target_amount, saved_amount: saved, deadline, months, needed_per_month: needed, current_monthly_surplus: surplus, gap, feasibility, suggested_deadline: suggested, cuts, cuts_total: cutsTotal, summary };
}

export function fixtureSurvival(id: string, amount?: number, until?: string, locale: Locale = 'en'): SurvivalPlan {
  fmtLocale = locale;
  const txs = generate(id).txs;
  const amt = amount ?? balanceOf(id);
  const end = until ?? nextPayday(id);
  const days = Math.max(1, diffDays(AS_OF, end));
  const bills = upcomingBills(id, end);
  const billsTotal = r2(bills.reduce((a, b) => a + b.amount, 0));
  const free = r2(amt - billsTotal);
  const perDay = r2(Math.max(0, free) / days);
  const typical = (cat: string, pred?: (t: Tx) => boolean) => r2((monthlyAvg(txs, (t) => isSpend(t) && t.category === cat && (!pred || pred(t))) * days) / 30);
  const pos = Math.max(0, free);
  const budgets = [
    { category: 'Groceries', budget: r2(pos * 0.6), typical: typical('Groceries') },
    { category: 'Transportation', budget: r2(pos * 0.15), typical: typical('Transportation', (t) => t.basket !== 'fixed') },
    { category: 'Restaurants', budget: r2(pos * 0.1), typical: typical('Restaurants') },
    { category: 'Other', budget: r2(pos * 0.15), typical: typical('Lifestyle') },
  ];
  const risk: SurvivalPlan['risk'] = free < 0 ? 'short' : perDay < 12 ? 'tight' : 'ok';
  const tips = tr(
    locale,
    ['Plan a weekly menu and do one bigger shop — fewer impulse stops.', 'Pause one streaming service for this month.', 'Take transit instead of taxis until payday.', 'If a bill is at risk, ask S-Bank about moving the due date before it is late.'],
    ['Tee viikon ruokalista ja yksi isompi ostosreissu – vähemmän heräteostoksia.', 'Tauota yksi suoratoistopalvelu tämän kuun ajaksi.', 'Kulje joukkoliikenteellä takseilla ajamisen sijaan palkkapäivään asti.', 'Jos lasku uhkaa myöhästyä, kysy S-Pankista eräpäivän siirtoa ajoissa.'],
    ['Gör en veckomeny och handla en gång större – färre impulsköp.', 'Pausa en streamingtjänst den här månaden.', 'Åk kollektivt i stället för taxi fram till lönen.', 'Om en räkning riskerar att bli sen, fråga S-Banken i tid om att flytta förfallodagen.'],
  );
  return { amount: r2(amt), until: end, days, upcoming_bills_total: billsTotal, bills, free_money: free, per_day: perDay, per_week: r2(perDay * 7), category_budgets: budgets, risk, shortfall: r2(Math.max(0, -free)), tips };
}

export function fixtureHomeReadiness(id: string, price?: number, locale: Locale = 'en'): HomeReadiness {
  fmtLocale = locale;
  const p = cfgFor(id);
  const txs = generate(id).txs;
  const propertyPrice = price ?? (p.customer.age > 35 ? 260000 : 180000);
  const ltv = 0.9;
  const loan = r2(propertyPrice * ltv);
  const equityNeeded = r2(propertyPrice - loan);
  const goalSaved = fixtureGoals(id, locale).filter((g) => g.kind === 'home' || g.kind === 'emergency').reduce((a, g) => a + g.saved_amount, 0);
  const equity = r2(Math.max(0, balanceOf(id) * 0.5 + goalSaved));
  // Stress-test at 6 % over 25 years; banks commonly expect the payment to fit in ~35 % of net income.
  const rate = 0.06 / 12;
  const n = 25 * 12;
  const payment = (loan * rate) / (1 - Math.pow(1 + rate, -n));
  const required = r2(payment / 0.35);
  const income = monthlyAvg(txs, (t) => t.basket === 'income');
  const gaps: string[] = [];
  const T = (en: string, fi: string, sv: string) => tr(locale, en, fi, sv);
  if (equity < equityNeeded) gaps.push(T(`Down payment short by ${fmt(equityNeeded - equity)} (10% of the price).`, `Omarahoitusta puuttuu ${fmt(equityNeeded - equity)} (10 % kauppahinnasta).`, `Det fattas ${fmt(equityNeeded - equity)} i egen insats (10 % av priset).`));
  if (income < required) gaps.push(T(`Stress-tested income need is ${fmt(required)}/mo, you have ${fmt(income)}/mo.`, `Stressitestattu tulotarve on ${fmt(required)}/kk, sinulla ${fmt(income)}/kk.`, `Stresstestat inkomstbehov är ${fmt(required)}/mån, du har ${fmt(income)}/mån.`));
  const leak = monthlyAvg(txs, (t) => t.basket === 'leak');
  const leakPct = Math.round((leak / income) * 100);
  if (leak > income * 0.2) gaps.push(T(`Leak basket is ${leakPct}% of income — lenders look at spending habits too.`, `Vuotokori on ${leakPct} % tuloista – pankki katsoo myös kulutustottumuksia.`, `Läckkorgen är ${leakPct} % av inkomsten – banken tittar också på dina konsumtionsvanor.`));
  const verdict: HomeReadiness['verdict'] = gaps.length === 0 ? 'ready' : gaps.length === 1 ? 'almost' : 'not_yet';
  return {
    property_price: propertyPrice,
    loan_needed: loan,
    equity_needed: equityNeeded,
    your_equity_estimate: equity,
    required_monthly_income: required,
    your_monthly_income: income,
    ltv,
    verdict,
    gaps,
    dataset_note: T('Based on income-to-loan ratios in 200 synthetic mortgage applications.', 'Perustuu 200 synteettisen asuntolainahakemuksen tulojen ja lainan suhteisiin.', 'Baserat på förhållandet mellan inkomst och lån i 200 syntetiska bolåneansökningar.'),
    customer_application: id === 'CUST00961' ? { status: 'rejected', requested_loan: 245000, reason: T('Down payment and savings history', 'Omarahoitus ja säästöhistoria', 'Egen insats och sparhistorik') } : null,
  };
}

/** One primary + at most two supporting recovery messages, essentials first. */
function recoveryNudges(rec: Recovery, sts: SafeToSpend, locale: Locale): Nudge[] {
  const T = (en: string, fi: string, sv: string) => tr(locale, en, fi, sv);
  const balance = fmtCents(Math.abs(rec.balance ?? 0));
  const deficit = fmt(rec.deficit ?? 0);
  const primary: Nudge =
    rec.state === 'balance_repair'
      ? {
          id: 'recovery_balance', kind: 'warn', emoji: '🔴',
          text: T(`Your account is ${balance} below zero. We start with everyday essentials and bills, not a savings challenge.`, `Tilisi on ${balance} miinuksella. Aloitetaan arjen välttämättömistä menoista ja laskuista, ei säästöhaasteesta.`, `Kontot är ${balance} under noll. Vi börjar med vardagens nödvändiga utgifter och räkningar, inte med en sparutmaning.`),
          action_prompt: T('How do I get back to a positive balance?', 'Miten pääsen takaisin plussalle?', 'Hur kommer jag tillbaka till plus?'),
        }
      : {
          id: 'recovery_cashflow', kind: 'warn', emoji: '📉',
          text: T(`Your balance is at or above zero (${balance}), but spending has averaged ${deficit} more than income over the last six full months — the buffer is shrinking.`, `Saldo on vähintään nollassa (${balance}), mutta kuuden täyden kuukauden menoja on ollut keskimäärin ${deficit} tuloja enemmän — puskuri hupenee.`, `Saldot är noll eller högre (${balance}), men utgifterna har varit i genomsnitt ${deficit} mer än inkomsten under de sex senaste hela månaderna — bufferten krymper.`),
          action_prompt: T('How do I stop my buffer from shrinking?', 'Miten estän puskurin hupenemisen?', 'Hur hindrar jag att bufferten krymper?'),
        };
  const supporting: Nudge[] = [];
  const bills = sts.upcoming_bills.filter((b) => b.basket !== 'saving');
  if (bills.length) {
    const total = fmt(bills.reduce((a, b) => a + b.amount, 0));
    supporting.push({
      id: 'recovery_bills', kind: 'tip', emoji: '📅',
      text: T(`Bills of about ${total} are due before payday. Let's check which are essential first.`, `Ennen palkkapäivää erääntyy laskuja noin ${total}. Tarkistetaan ensin, mitkä niistä ovat välttämättömiä.`, `Räkningar på ungefär ${total} förfaller före lönedagen. Vi kontrollerar först vilka som är nödvändiga.`),
      action_prompt: T('How do I make it to payday — which bills come first?', 'Miten selviän palkkapäivään asti ja mitkä laskut tulevat ensin?', 'Hur klarar jag mig till lönedagen och vilka räkningar kommer först?'),
    });
  }
  if ((rec.monthly_surplus ?? 0) < 0) {
    supporting.push({
      id: 'recovery_deficit', kind: 'warn', emoji: '📉',
      text: T(`Over the last six full months spending has averaged ${deficit} more than income. Shall we look at where that difference comes from?`, `Viimeisten kuuden täyden kuukauden aikana menoja on ollut keskimäärin ${deficit} tuloja enemmän. Katsotaanko, mistä ero muodostuu?`, `Under de sex senaste hela månaderna har utgifterna varit i genomsnitt ${deficit} mer än inkomsten. Ska vi titta på var skillnaden kommer från?`),
      action_prompt: T('Where does the six-month spending gap come from?', 'Mistä kuuden kuukauden menoero muodostuu?', 'Var kommer utgiftsgapet på sex månader från?'),
    });
  } else {
    const surplus = fmt(rec.monthly_surplus ?? 0);
    supporting.push({
      id: 'recovery_cashflow_positive', kind: 'tip', emoji: '📈',
      text: T(`The last six full months averaged a surplus of ${surplus}/month. Let's check the current situation separately.`, `Kuuden täyden kuukauden ylijäämä oli keskimäärin ${surplus}/kk. Tarkistetaan nykytilanne erikseen.`, `De senaste sex hela månaderna gav ett överskott på i genomsnitt ${surplus}/mån. Vi kontrollerar nuläget separat.`),
      action_prompt: T('Where does the six-month spending gap come from?', 'Mistä kuuden kuukauden menoero muodostuu?', 'Var kommer utgiftsgapet på sex månader från?'),
    });
    supporting.push({
      id: 'recovery_buffer', kind: 'tip', emoji: '🛟',
      text: T('When affordable, a small buffer can help with unexpected expenses.', 'Kun rahaa jää yli, pieni puskuri voi auttaa yllättävissä menoissa.', 'När det finns utrymme kan en liten buffert hjälpa med oväntade utgifter.'),
      action_prompt: T('What is an emergency buffer and how do I start one?', 'Mikä on puskurirahasto ja miten aloitan sen?', 'Vad är en buffert och hur börjar jag en?'),
    });
  }
  const out = [primary, ...supporting.slice(0, 2)];
  if (out.length < 3)
    out.push({
      id: 'recovery_essentials', kind: 'tip', emoji: '🧾',
      text: T('Start with essentials: food, housing, medicines, transport. Leaks can wait.', 'Aloitetaan välttämättömistä menoista: ruoka, asuminen, lääkkeet, liikkuminen. Vuodot odottavat.', 'Börja med det nödvändiga: mat, boende, medicin, transport. Läckorna kan vänta.'),
      action_prompt: T('How do I make my money last until payday?', 'Miten saan rahani riittämään palkkapäivään asti?', 'Hur får jag pengarna att räcka till lönedagen?'),
    });
  return out;
}

function unknownNudges(locale: Locale): Nudge[] {
  const T = (en: string, fi: string, sv: string) => tr(locale, en, fi, sv);
  return [
    {
      id: 'recovery_unknown', kind: 'tip', emoji: '❔',
      text: T('I do not have enough information, so I will not guess whether you are in the black.', 'Tietoja ei ole riittävästi, joten en arvaa, oletko plussalla vai et.', 'Jag har inte tillräckligt med information, så jag gissar inte om du är på plus.'),
      action_prompt: T('What is my current money situation?', 'Mikä on rahatilanteeni nyt?', 'Hur ser min pengasituation ut?'),
    },
    {
      id: 'learn', kind: 'tip', emoji: '🧺',
      text: T('Fixed, irregular, leaks: know your three money baskets.', 'Kiinteät, epäsäännölliset, vuodot: tunne kolme rahakoriasi.', 'Fasta, oregelbundna, läckor: lär känna dina tre pengakorgar.'),
      action_prompt: T('Explain the three money baskets', 'Selitä kolme rahakoria', 'Förklara de tre pengakorgarna'),
    },
  ];
}

export function fixtureNudges(id: string, locale: Locale = 'en'): Nudge[] {
  fmtLocale = locale;
  const txs = generate(id).txs;
  const sts = fixtureSafeToSpend(id, locale);
  const T = (en: string, fi: string, sv: string) => tr(locale, en, fi, sv);
  const recoveryState = fixtureRecovery(id, locale);
  if (recoveryState.state === 'balance_repair' || recoveryState.state === 'cashflow_stabilizing')
    return recoveryNudges(recoveryState, sts, locale);
  if (recoveryState.state === 'unknown') return unknownNudges(locale);
  const out: Nudge[] = [];
  const cafeThis = sumAbs(txs.filter((t) => t.date >= monthStart(AS_OF) && t.category === 'Restaurants'));
  const cafeAvgToDate = (monthlyAvg(txs, (t) => t.category === 'Restaurants') * Number(AS_OF.slice(8))) / 30;
  if (sts.status !== 'comfortable')
    out.push({ id: 'n-safe', kind: 'warn', emoji: '🧯', text: T(`${sts.days_until_payday} days to payday — safe to spend ${fmt(sts.safe_per_day)} a day.`, `Palkkapäivään ${sts.days_until_payday} päivää – käyttövaraa ${fmt(sts.safe_per_day)} päivässä.`, `${sts.days_until_payday} dagar till lönen – tryggt att använda ${fmt(sts.safe_per_day)} per dag.`), action_prompt: T('How do I make it to payday?', 'Miten selviän palkkapäivään?', 'Hur klarar jag mig till lönen?') });
  if (cafeThis > cafeAvgToDate * 1.1)
    out.push({ id: 'n-rest', kind: 'warn', emoji: '🍔', text: T(`Eating out is at ${fmt(cafeThis)} this month — above your usual pace.`, `Ulkona syömiseen on mennyt tässä kuussa ${fmt(cafeThis)} – tavallista enemmän.`, `Att äta ute har kostat ${fmt(cafeThis)} den här månaden – mer än vanligt.`), action_prompt: T('How much could I save if I reduced dining out by 20%?', 'Paljonko säästäisin, jos söisin ulkona 20 % vähemmän?', 'Hur mycket skulle jag spara om jag åt ute 20 % mindre?') });
  else
    out.push({ id: 'n-rest', kind: 'celebrate', emoji: '🏆', text: T(`Eating out is under control this month (${fmt(cafeThis)}). Nice work!`, `Ravintolakulut pysyvät tässä kuussa kurissa (${fmt(cafeThis)}). Hienoa!`, `Restaurangutgifterna håller sig i schack den här månaden (${fmt(cafeThis)}). Snyggt!`), action_prompt: T('What kind of spender am I?', 'Millainen kuluttaja olen?', 'Hurdan konsument är jag?') });
  const g = fixtureGoals(id, locale).find((x) => x.progress < 1);
  if (g) {
    const deficit = monthlySurplus(id) < g.monthly_contribution;
    out.push({ id: 'n-goal', kind: 'goal', emoji: g.emoji, text: deficit
      ? T(`${g.name}: ${Math.round(g.progress * 100)}% there. ${fmt(g.monthly_contribution)}/month is more than you currently have left over.`, `${g.name}: ${Math.round(g.progress * 100)} % kasassa. ${fmt(g.monthly_contribution)}/kk on enemmän kuin sinulle nyt jää yli.`, `${g.name}: ${Math.round(g.progress * 100)} % klart. ${fmt(g.monthly_contribution)}/mån är mer än du har över just nu.`)
      : T(`${g.name}: ${Math.round(g.progress * 100)}% there. ${fmt(g.monthly_contribution)}/month gets you to the finish.`, `${g.name}: ${Math.round(g.progress * 100)} % kasassa. ${fmt(g.monthly_contribution)}/kk vie maaliin.`, `${g.name}: ${Math.round(g.progress * 100)} % klart. ${fmt(g.monthly_contribution)}/mån tar dig i mål.`), action_prompt: T(`How can I reach my ${g.name} goal faster?`, `Miten saavutan tavoitteen ${g.name} nopeammin?`, `Hur når jag mitt sparmål ${g.name} snabbare?`) });
  }
  const rec = fixtureRecurring(id);
  out.push({ id: 'n-subs', kind: 'tip', emoji: '📺', text: T(`${rec.items.length} recurring payments — ${fmt(rec.monthly_total)}/month on autopilot.`, `${rec.items.length} toistuvaa maksua – ${fmt(rec.monthly_total)}/kk lähtee automaattisesti.`, `${rec.items.length} återkommande betalningar – ${fmt(rec.monthly_total)}/mån dras automatiskt.`), action_prompt: T('Show my subscriptions and recurring payments', 'Näytä toistuvat maksuni', 'Visa mina återkommande betalningar') });
  out.push({ id: 'n-tip', kind: 'tip', emoji: '🧺', text: T('Did you know? Your money splits into three baskets. See yours.', 'Tiesitkö? Rahasi jakautuvat kolmeen koriin. Katso omasi.', 'Visste du? Dina pengar fördelar sig på tre korgar. Se dina.'), action_prompt: T('Where does my money go this month?', 'Mihin rahani menevät tässä kuussa?', 'Vart går mina pengar den här månaden?') });
  return out;
}

export function fixtureOverview(id: string, locale: Locale = 'en'): Overview {
  const p = cfgFor(id);
  const txs = generate(id).txs;
  const monthTx = txs.filter((t) => t.date >= monthStart(AS_OF) && t.date <= AS_OF);
  const byB = (b: Basket) => sumAbs(monthTx.filter((t) => t.basket === b));
  const trend: { date: string; balance: number }[] = [];
  let last = txs.find((t) => t.date >= addDays(AS_OF, -30))?.balance_after ?? p.finalBalance;
  for (let d = addDays(AS_OF, -29); d <= AS_OF; d = addDays(d, 1)) {
    const day = txs.filter((t) => t.date === d);
    if (day.length) last = day[day.length - 1].balance_after;
    trend.push({ date: d, balance: last });
  }
  return {
    customer: { id: p.customer.customer_id, name: p.customer.name, age: p.customer.age, postal_code: p.customer.postal_code },
    as_of: AS_OF,
    balance: balanceOf(id),
    trend_30d: trend,
    month: { income: byB('income'), spent: r2(byB('fixed') + byB('irregular') + byB('leak')), saved: byB('saving'), by_basket: { fixed: byB('fixed'), irregular: byB('irregular'), leak: byB('leak') } },
    safe_to_spend: fixtureSafeToSpend(id, locale),
    recovery: fixtureRecovery(id, locale),
    goals: fixtureGoals(id, locale),
    recent_transactions: txs.filter((t) => t.date <= AS_OF).slice(-8).reverse(),
    nudges: fixtureNudges(id, locale),
  };
}

// ───────────────────────── lessons (Money Gym) ─────────────────────────

type LessonSrc = Omit<Lesson, 'title' | 'body' | 'summary' | 'quiz'> & {
  t: [string, string];
  s: [string, string];
  b: [string, string];
  q: { question: [string, string]; options: [string[], string[]]; answer_index: number; explanation: [string, string] };
};

const LESSONS: LessonSrc[] = [
  {
    id: 'three-baskets', emoji: '🧺', basket: null, topic: 'budgeting', level: 1, minutes: 2, tags: ['all'],
    t: ['The three baskets', 'Kolme koria'],
    s: ['Every euro you spend lands in one of three baskets.', 'Jokainen euro päätyy yhteen kolmesta korista.'],
    b: [
      '**Fixed essentials** are must-pay and regular: rent, electricity, groceries, transit pass.\n**Irregular essentials** are must-pay but surprise you: dentist, car repair, a new winter coat.\n**Everyday leaks** are choices: cafés, takeaway, taxis, impulse shopping.\n\nPlan the first basket, save monthly for the second, and steer the third — it is where most people find their money.',
      '**Kiinteät pakolliset** ovat säännöllisiä: vuokra, sähkö, ruoka, matkakortti.\n**Epäsäännölliset pakolliset** yllättävät: hammaslääkäri, auton korjaus, uusi talvitakki.\n**Arjen vuodot** ovat valintoja: kahvilat, noudot, taksit, heräteostokset.\n\nSuunnittele ensimmäinen kori, säästä kuukausittain toiseen ja ohjaa kolmatta — sieltä useimmat löytävät rahansa.',
    ],
    q: { question: ['A taxi home after a night out goes into which basket?', 'Taksi kotiin illanvieton jälkeen kuuluu mihin koriin?'], options: [['Fixed essentials', 'Irregular essentials', 'Everyday leaks'], ['Kiinteät pakolliset', 'Epäsäännölliset pakolliset', 'Arjen vuodot']], answer_index: 2, explanation: ['It is a choice, not a must — a classic leak.', 'Se on valinta, ei pakko — klassinen vuoto.'] },
  },
  {
    id: 'latte-factor', emoji: '☕', basket: 'leak', topic: 'leaks', level: 1, minutes: 2, tags: ['latte_leaker', 'weekend_treater', 'tightrope_walker'],
    t: ['Small buys, big sums', 'Pienet ostot, isot summat'],
    s: ['Why €4 a day is €1 460 a year.', 'Miksi 4 €/päivä on 1 460 €/vuosi.'],
    b: [
      'Small purchases do not feel like spending because each one is tiny. But frequency multiplies: a €4 coffee five times a week is about **€1 040 a year**.\n\nYou do not need to quit — try the **"2 of 5" rule**: keep the treat two days, skip it three. You keep the joy and free up a few hundred euros a year.',
      'Pienet ostot eivät tunnu kulutukselta, koska jokainen on pieni. Mutta toisto kertautuu: 4 €:n kahvi viidesti viikossa on noin **1 040 € vuodessa**.\n\nEi tarvitse lopettaa — kokeile **"2/5-sääntöä"**: herkuttele kahtena päivänä, jätä väliin kolmena. Ilo säilyy ja vuodessa vapautuu satoja euroja.',
    ],
    q: { question: ['€6 takeaway lunch 4× a week. Roughly how much per year?', '6 € noutolounas 4× viikossa. Paljonko vuodessa?'], options: [['≈ €300', '≈ €1 250', '≈ €3 000'], ['≈ 300 €', '≈ 1 250 €', '≈ 3 000 €']], answer_index: 1, explanation: ['6 × 4 × 52 = €1 248.', '6 × 4 × 52 = 1 248 €.'] },
  },
  {
    id: 'emergency-fund', emoji: '🛟', basket: 'irregular', topic: 'saving', level: 1, minutes: 3, tags: ['tightrope_walker', 'latte_leaker', 'all'],
    t: ['Your emergency fund', 'Puskurirahasto'],
    s: ['The buffer that turns surprises into non-events.', 'Puskuri, joka tekee yllätyksistä arkea.'],
    b: [
      'Irregular essentials will happen — you just do not know when. An **emergency fund** of 1–3 months of fixed costs means a broken phone is an inconvenience, not a crisis (or a high-interest loan).\n\nStart tiny: an automatic transfer on payday, even €20, builds the habit. Keep it in a separate savings account so it is not "spending money".',
      'Epäsäännölliset menot tulevat — et vain tiedä milloin. **Puskurirahasto**, joka kattaa 1–3 kuukauden kiinteät menot, tekee rikkinäisestä puhelimesta harmin eikä kriisiä (tai kallista pikalainaa).\n\nAloita pienestä: automaattinen siirto palkkapäivänä, vaikka 20 €, rakentaa tavan. Pidä se erillisellä säästötilillä.',
    ],
    q: { question: ['A good first target for an emergency fund is…', 'Hyvä ensimmäinen tavoite puskurille on…'], options: [['1 month of fixed costs', 'A full year of income', 'Whatever is left at month end'], ['1 kuukauden kiinteät menot', 'Koko vuoden tulot', 'Mitä kuun lopussa jää']], answer_index: 0, explanation: ['Start with one month, then grow towards three.', 'Aloita yhdestä kuukaudesta ja kasvata kohti kolmea.'] },
  },
  {
    id: 'pay-yourself-first', emoji: '🐷', basket: null, topic: 'saving', level: 2, minutes: 2, tags: ['weekend_treater', 'steady_planner', 'latte_leaker'],
    t: ['Pay yourself first', 'Maksa ensin itsellesi'],
    s: ['Save on payday, not at the end of the month.', 'Säästä palkkapäivänä, ei kuun lopussa.'],
    b: [
      'If you save "what is left", there is rarely anything left — spending expands to fill the account. Flip the order: on payday, move your goal amount automatically **first**, then live on the rest.\n\nThis is why people with the same income can have very different savings.',
      'Jos säästät "sen mitä jää", jää harvoin mitään — kulutus täyttää tilin. Käännä järjestys: siirrä palkkapäivänä tavoitesumma automaattisesti **ensin** ja elä lopulla.\n\nSiksi samoilla tuloilla voi olla hyvin erilaiset säästöt.',
    ],
    q: { question: ['When is the best moment to move money to savings?', 'Milloin on paras hetki siirtää rahaa säästöön?'], options: [['Right after payday', 'On the last day of the month', 'When the balance looks high'], ['Heti palkkapäivän jälkeen', 'Kuun viimeisenä päivänä', 'Kun saldo näyttää isolta']], answer_index: 0, explanation: ['Automate it on payday — you never "see" the money.', 'Automatisoi palkkapäivään — et edes "näe" rahaa.'] },
  },
  {
    id: 'subscriptions', emoji: '📺', basket: 'fixed', topic: 'fixed', level: 1, minutes: 2, tags: ['tightrope_walker', 'weekend_treater', 'all'],
    t: ['Subscription autopilot', 'Tilausten autopilotti'],
    s: ['Recurring payments are fixed costs you chose.', 'Toistuvat maksut ovat itse valittuja kiinteitä menoja.'],
    b: [
      'Streaming, apps, gym — each is small, but together they quietly become a fixed cost. Once a quarter, list them and ask: **did I use this last month?** Pause what you did not.\n\nRotating one streaming service at a time often saves €100+ a year with zero pain.',
      'Suoratoisto, sovellukset, sali — jokainen on pieni, mutta yhdessä niistä tulee hiljaa kiinteä meno. Kerran neljännesvuodessa listaa ne ja kysy: **käytinkö tätä viime kuussa?** Tauota loput.\n\nYhden suoratoistopalvelun vuorottelu säästää usein yli 100 € vuodessa.',
    ],
    q: { question: ['Which habit keeps subscriptions in check?', 'Mikä tapa pitää tilaukset kurissa?'], options: [['Review them every quarter', 'Pay them yearly upfront always', 'Never cancel anything'], ['Käy ne läpi neljännesvuosittain', 'Maksa aina vuodeksi etukäteen', 'Älä koskaan peru mitään']], answer_index: 0, explanation: ['A regular review catches the ones you stopped using.', 'Säännöllinen läpikäynti löytää käyttämättömät.'] },
  },
  {
    id: 'compound-growth', emoji: '🌱', basket: null, topic: 'investing', level: 2, minutes: 3, tags: ['squirrel_saver', 'steady_planner', 'weekend_treater'],
    t: ['Time & compound growth', 'Aika ja korkoa korolle'],
    s: ['Why starting early beats starting big.', 'Miksi aikainen aloitus voittaa ison aloituksen.'],
    b: [
      'When returns earn returns, growth snowballs. €50 a month for 20 years is €12 000 saved — at a 5 % average return it could grow to roughly **€20 000**.\n\nInvesting always carries risk: values go up and down, and past returns do not guarantee future ones. This is general education, not advice — S-Bank advisors can help you choose what fits you.',
      'Kun tuotto tuottaa tuottoa, kasvu kiihtyy. 50 €/kk 20 vuotta on 12 000 € säästöä — 5 %:n keskituotolla se voisi kasvaa noin **20 000 euroon**.\n\nSijoittamiseen liittyy aina riski: arvot heiluvat, eikä aiempi tuotto takaa tulevaa. Tämä on yleistä tietoa, ei neuvontaa — S-Pankin asiantuntijat auttavat valitsemaan sinulle sopivan.',
    ],
    q: { question: ['What makes compound growth powerful?', 'Mikä tekee korkoa korolle -ilmiöstä tehokkaan?'], options: [['Time in the market', 'Guaranteed returns', 'Picking one hot stock'], ['Aika', 'Taatut tuotot', 'Yhden kuuman osakkeen valinta']], answer_index: 0, explanation: ['Time lets returns build on returns. Nothing is guaranteed.', 'Aika antaa tuottojen kasvaa tuottojen päälle. Mikään ei ole taattua.'] },
  },
  {
    id: 'payday-cycle', emoji: '📅', basket: 'fixed', topic: 'cashflow', level: 1, minutes: 2, tags: ['tightrope_walker', 'latte_leaker'],
    t: ['Surviving the payday cycle', 'Palkkapäivästä palkkapäivään'],
    s: ['Turn "balance" into "safe to spend per day".', 'Muuta saldo "turvalliseksi päiväbudjetiksi".'],
    b: [
      'Your balance lies: part of it already belongs to rent and bills due before payday. **Safe to spend** = balance − upcoming bills − a small buffer, divided by days left.\n\nChecking a daily number is far easier than tracking a monthly budget — and it warns you early.',
      'Saldo valehtelee: osa siitä kuuluu jo vuokralle ja laskuille ennen palkkapäivää. **Turvallisesti käytettävissä** = saldo − tulevat laskut − pieni puskuri, jaettuna jäljellä olevilla päivillä.\n\nPäiväsumman seuraaminen on paljon helpompaa kuin kuukausibudjetin — ja se varoittaa ajoissa.',
    ],
    q: { question: ['Balance €300, bills before payday €180, 10 days left. Safe per day?', 'Saldo 300 €, laskut ennen palkkaa 180 €, 10 päivää. Turvallisesti/päivä?'], options: [['€30', '€12', '€18'], ['30 €', '12 €', '18 €']], answer_index: 1, explanation: ['(300 − 180) / 10 = €12 (before any buffer).', '(300 − 180) / 10 = 12 € (ennen puskuria).'] },
  },
  {
    id: 'home-readiness', emoji: '🏡', basket: null, topic: 'mortgage', level: 3, minutes: 3, tags: ['steady_planner', 'squirrel_saver'],
    t: ['Getting mortgage-ready', 'Valmiiksi asuntolainaan'],
    s: ['What a bank looks at before saying yes.', 'Mitä pankki katsoo ennen myöntävää päätöstä.'],
    b: [
      'For a first home in Finland you typically need **5–10 % down payment**. Banks also stress-test your loan at a higher interest rate (often 6 %) to make sure payments stay affordable.\n\nSteady savings history matters as much as the lump sum: regular monthly saving shows you can carry the payment.',
      'Ensiasuntoon tarvitset Suomessa yleensä **5–10 % omarahoitusta**. Pankki myös stressitestaa lainan korkeammalla korolla (usein 6 %), jotta maksut pysyvät kohtuullisina.\n\nSäännöllinen säästöhistoria on yhtä tärkeä kuin summa: kuukausittainen säästäminen näyttää, että jaksat maksaa lainaa.',
    ],
    q: { question: ['Why do banks stress-test at a higher rate?', 'Miksi pankit stressitestaavat korkeammalla korolla?'], options: [['To check you can still pay if rates rise', 'To charge more interest', 'It is only for business loans'], ['Varmistaakseen maksukyvyn korkojen noustessa', 'Periäkseen enemmän korkoa', 'Vain yrityslainoille']], answer_index: 0, explanation: ['Rates change over a 25-year loan; the test protects you.', 'Korot muuttuvat 25 vuodessa; testi suojaa sinua.'] },
  },
];

type LessonTextSv = { t: string; s: string; b: string; q: { question: string; options: string[]; explanation: string } };

/** Swedish lesson texts, keyed by lesson id (same structure and quiz answers as LESSONS). */
const LESSONS_SV: Record<string, LessonTextSv> = {
  'three-baskets': {
    t: 'De tre korgarna',
    s: 'Varje euro du gör av med hamnar i en av tre korgar.',
    b: '**Fasta nödvändiga utgifter** måste betalas regelbundet: hyra, el, mat, månadskort.\n**Oregelbundna nödvändiga utgifter** måste betalas men kommer som överraskningar: tandläkare, bilreparation, en ny vinterjacka.\n**Vardagsläckor** är val: kaféer, hämtmat, taxi, impulsköp.\n\nPlanera den första korgen, spara varje månad till den andra och styr den tredje – där hittar de flesta sina pengar.',
    q: { question: 'Taxi hem efter en kväll ute – vilken korg hör den till?', options: ['Fasta nödvändiga', 'Oregelbundna nödvändiga', 'Vardagsläckor'], explanation: 'Det är ett val, inte ett måste – en klassisk läcka.' },
  },
  'latte-factor': {
    t: 'Små köp, stora summor',
    s: 'Varför 4 € om dagen blir 1 460 € om året.',
    b: 'Små köp känns inte som utgifter eftersom vart och ett är litet. Men upprepningen multiplicerar: en kaffe för 4 € fem gånger i veckan blir cirka **1 040 € om året**.\n\nDu behöver inte sluta – testa **”2 av 5”-regeln**: unna dig två dagar och hoppa över tre. Glädjen finns kvar och några hundra euro om året frigörs.',
    q: { question: 'Hämtlunch för 6 € fyra gånger i veckan. Ungefär hur mycket per år?', options: ['≈ 300 €', '≈ 1 250 €', '≈ 3 000 €'], explanation: '6 × 4 × 52 = 1 248 €.' },
  },
  'emergency-fund': {
    t: 'Din buffert',
    s: 'Bufferten som gör överraskningar till vardag.',
    b: 'Oregelbundna utgifter kommer – du vet bara inte när. En **buffert** som täcker 1–3 månaders fasta utgifter gör en trasig telefon till ett irritationsmoment i stället för en kris (eller ett dyrt snabblån).\n\nBörja smått: en automatisk överföring på lönedagen, även 20 €, bygger upp vanan. Håll pengarna på ett separat sparkonto.',
    q: { question: 'Ett bra första mål för bufferten är…', options: ['1 månads fasta utgifter', 'Ett helt års inkomst', 'Det som blir kvar i slutet av månaden'], explanation: 'Börja med en månad och bygg sedan upp mot tre.' },
  },
  'pay-yourself-first': {
    t: 'Betala dig själv först',
    s: 'Spara på lönedagen, inte i slutet av månaden.',
    b: 'Om du sparar ”det som blir över” blir det sällan något över – utgifterna fyller kontot. Vänd på ordningen: flytta sparbeloppet automatiskt **först** på lönedagen och lev på resten.\n\nDärför kan personer med samma inkomst ha väldigt olika sparande.',
    q: { question: 'När är det bästa tillfället att flytta pengar till sparande?', options: ['Direkt efter lönedagen', 'Månadens sista dag', 'När saldot ser högt ut'], explanation: 'Automatisera det på lönedagen – då ”ser” du aldrig pengarna.' },
  },
  subscriptions: {
    t: 'Prenumerationer på autopilot',
    s: 'Återkommande betalningar är fasta utgifter som du själv har valt.',
    b: 'Streaming, appar, gym – var för sig små, men tillsammans blir de i det tysta en fast utgift. En gång per kvartal: lista dem och fråga dig **använde jag det här förra månaden?** Pausa det du inte använde.\n\nAtt rotera en streamingtjänst i taget sparar ofta över 100 € om året utan att det känns.',
    q: { question: 'Vilken vana håller prenumerationerna i schack?', options: ['Gå igenom dem varje kvartal', 'Betala alltid ett år i förskott', 'Säg aldrig upp något'], explanation: 'En regelbunden genomgång hittar dem du har slutat använda.' },
  },
  'compound-growth': {
    t: 'Tid och ränta på ränta',
    s: 'Varför en tidig start slår en stor start.',
    b: 'När avkastningen ger avkastning växer pengarna som en snöboll. 50 € i månaden i 20 år är 12 000 € sparat – med 5 % genomsnittlig avkastning kunde det växa till ungefär **20 000 €**.\n\nInvesteringar innebär alltid risk: värdet går upp och ner, och tidigare avkastning är ingen garanti för framtida. Det här är allmän information, inte rådgivning – S-Bankens experter hjälper dig att välja det som passar dig.',
    q: { question: 'Vad gör ränta på ränta så kraftfull?', options: ['Tid', 'Garanterad avkastning', 'Att välja en het aktie'], explanation: 'Tiden låter avkastningen växa ovanpå avkastningen. Inget är garanterat.' },
  },
  'payday-cycle': {
    t: 'Från lön till lön',
    s: 'Gör om saldot till ”tryggt att använda per dag”.',
    b: 'Saldot ljuger: en del av det hör redan till hyran och räkningarna före lönen. **Tryggt att använda** = saldo − kommande räkningar − en liten buffert, delat med antalet dagar kvar.\n\nAtt följa en dagssumma är mycket lättare än att följa en månadsbudget – och den varnar i tid.',
    q: { question: 'Saldo 300 €, räkningar före lönen 180 €, 10 dagar kvar. Hur mycket är tryggt per dag?', options: ['30 €', '12 €', '18 €'], explanation: '(300 − 180) / 10 = 12 € (före buffert).' },
  },
  'home-readiness': {
    t: 'Redo för bolån',
    s: 'Vad banken tittar på innan den säger ja.',
    b: 'För en första bostad i Finland behöver du vanligtvis **5–10 % egen insats**. Banken stresstestar också lånet med en högre ränta (ofta 6 %) för att se att du klarar betalningarna.\n\nEn jämn sparhistorik väger lika tungt som summan: regelbundet månadssparande visar att du klarar av att betala lånet.',
    q: { question: 'Varför stresstestar bankerna med en högre ränta?', options: ['För att se att du klarar betalningarna om räntan stiger', 'För att ta ut mer ränta', 'Det gäller bara företagslån'], explanation: 'Räntorna ändras under ett lån på 25 år; testet skyddar dig.' },
  },
};

export function fixtureLessons(locale: Locale = 'en'): Lesson[] {
  const i = locale === 'fi' ? 1 : 0;
  return LESSONS.map(({ t, s, b, q, ...rest }) => {
    const sv = locale === 'sv' ? LESSONS_SV[rest.id] : undefined;
    return {
      ...rest,
      title: sv?.t ?? t[i],
      summary: sv?.s ?? s[i],
      body: sv?.b ?? b[i],
      quiz: { question: sv?.q.question ?? q.question[i], options: sv?.q.options ?? q.options[i], answer_index: q.answer_index, explanation: sv?.q.explanation ?? q.explanation[i] },
    };
  });
}

// ───────────────────────── chat stream fixture ─────────────────────────

/** Locale used by `fmt` for numbers embedded in fixture sentences (set by each localised entry point). */
let fmtLocale: Locale = 'en';

/** Picks the en / fi / sv variant. */
function tr<T>(locale: Locale, en: T, fi: T, sv: T): T {
  return locale === 'fi' ? fi : locale === 'sv' ? sv : en;
}

/** Money inside fixture sentences: "1 234 €" / "12,50 €" (NBSP) for fi & sv, "€1,234" / "€12.50" for en. */
function fmt(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? '−' : '';
  if (fmtLocale === 'en') {
    const s = abs >= 100 ? Math.round(abs).toLocaleString('en-US') : abs.toFixed(2).replace(/\.00$/, '');
    return `${sign}€${s}`;
  }
  const s = abs >= 100 ? String(Math.round(abs)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ') : abs.toFixed(2).replace(/\.00$/, '').replace('.', ',');
  return `${sign}${s} €`;
}

/** Money to the cent — used when the advice turns on the exact balance. */
function fmtCents(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? '−' : '';
  const s = abs.toFixed(2);
  return fmtLocale === 'en' ? `${sign}€${s}` : `${sign}${s.replace('.', ',')} €`;
}

const has = (q: string, words: string[]) => words.some((w) => q.includes(w));

type Plan = { label: string; tool: string; args: Record<string, unknown>; widgets: Widget[]; text: string; mood: 'happy' | 'neutral' | 'concerned' | 'celebrate'; suggestions: string[]; txCount: number };

/** Language of the reply: the language of the question when it is clear, else the requested locale (SPEC §5.6). */
function replyLocale(req: ChatRequest): Locale {
  const last = [...req.messages].reverse().find((m) => m.role === 'user')?.content ?? '';
  return detectLanguage(last, req.locale);
}

function planChat(req: ChatRequest): Plan {
  const lang = replyLocale(req);
  fmtLocale = lang;
  const id = req.customer_id;
  const sisu = req.persona === 'sisu';
  const name = cfgFor(id).customer.name;
  const last = [...req.messages].reverse().find((m) => m.role === 'user')?.content ?? '';
  const q = last.toLowerCase();
  const wid = (type: string, data: unknown): Widget => ({ id: `w-${type}-${Math.random().toString(36).slice(2, 8)}`, type, data });
  const prevMonthStart = addMonths(monthStart(AS_OF), -1);
  const prevMonthEnd = addDays(monthStart(AS_OF), -1);
  const T = (en: string, fi: string, sv: string) => tr(lang, en, fi, sv);
  const S3 = (en: string[], fi: string[], sv: string[]) => tr(lang, en, fi, sv);
  const pc = (n: number) => (lang === 'en' ? `${n}%` : `${n} %`);
  const rec = fixtureRecovery(id, lang);
  const recovering = rec.state === 'balance_repair' || rec.state === 'cashflow_stabilizing';
  const recoverySuggestions = S3(['Which bills are coming up?', 'Where does the six-month spending gap come from?', 'How do I make it to payday?'], ['Mitä laskuja on tulossa?', 'Mistä kuuden kuukauden menoero muodostuu?', 'Miten selviän palkkapäivään asti?'], ['Vilka räkningar är på väg?', 'Var kommer utgiftsgapet på sex månader från?', 'Hur klarar jag mig till lönedagen?']);
  const essentials = T('Check food, housing, medicines and transport before goal transfers. If essentials do not fit, S-Bank customer service or free public debt advice can help.', 'Tarkistetaan ruoka, asuminen, lääkkeet ja liikkuminen ennen tavoitesiirtoja. Jos rahat eivät riitä välttämättömään, S-Pankin asiakaspalvelu tai maksuton talous- ja velkaneuvonta voi auttaa.', 'Kontrollera mat, boende, mediciner och transport före målöverföringar. Om pengarna inte räcker till det nödvändiga kan S-Bankens kundtjänst eller gratis ekonomi- och skuldrådgivning hjälpa.');
  if (rec.state === 'unknown') return {
    label: T('Checking your situation…', 'Tarkistan tilanteesi…', 'Kontrollerar läget…'), tool: 'get_overview', args: {}, txCount: 0, widgets: [],
    text: T('There is not enough information to assess your situation.', 'Tietoja ei ole riittävästi tilanteen arvioimiseen.', 'Det finns inte tillräckligt med information för att bedöma läget.'), mood: 'neutral', suggestions: recoverySuggestions,
  };

  if (has(q, ['show my goals', 'show goals', 'näytä tavoitte', 'visa mina mål', 'visa mål', 'visa mina sparmål'])) {
    const goals = fixtureGoals(id, lang);
    return { label: T('Your goals', 'Tavoitteesi', 'Dina mål'), tool: 'list_goals', args: {}, txCount: 0,
      widgets: goals.length ? [
        wid('kpi', { items: goals.slice(0, 4).map((g) => ({ label: `${g.emoji} ${g.name}`, value: Math.round(g.progress * 1000) / 10, unit: '%', tone: g.progress >= 0.5 ? 'good' : 'neutral' })) }),
        wid('action_buttons', { buttons: [{ label: T('Open goals', 'Avaa tavoitteet', 'Öppna sparmål'), kind: 'open_tab', payload: { tab: 'goals' } }] }),
      ] : [],
      text: goals.map((g) => `${g.name}: ${fmt(g.saved_amount)} / ${fmt(g.target_amount)}`).join('. ') + (recovering ? ` ${essentials}` : ''),
      mood: recovering ? 'concerned' : 'neutral', suggestions: recoverySuggestions };
  }

  // Recovery questions (and the recovery nudge actions) answer from the same snapshot.
  if (has(q, ['back to a positive balance', 'back in the black', 'takaisin plussalle', 'tillbaka till plus',
    'below zero', 'miinuksella', 'under noll', 'buffer from shrinking', 'stop my buffer',
    'puskurin hupen', 'puskurin krymp', 'bufferten krymp', 'hindrar jag att buffert',
    'rahatilanteeni', 'pengasituation']) && !has(q, ['tavoite', 'goal', 'sparmål', 'målet'])) {
    const balance = fmtCents(rec.balance ?? 0);
    const deficit = fmt(rec.deficit ?? 0);
    const surplus = fmt(Math.abs(rec.monthly_surplus ?? 0));
    const need = fmt(rec.goal_monthly_need);
    const planned = rec.planned_monthly_change === null ? null : fmt(rec.planned_monthly_change);
    const trend = (rec.monthly_surplus ?? 0) < 0
      ? T(`Over the last six full months spending has averaged ${deficit} more than income.`, `Viimeisten kuuden täyden kuukauden aikana menoja on ollut keskimäärin ${deficit} tuloja enemmän.`, `Under de sex senaste hela månaderna har utgifterna varit i genomsnitt ${deficit} mer än inkomsten.`)
      : T(`The last six full months averaged a surplus of ${surplus}/month. Let's check the current situation separately.`, `Kuuden täyden kuukauden ylijäämä oli keskimäärin ${surplus}/kk. Tarkistetaan nykytilanne erikseen.`, `De senaste sex hela månaderna gav ett överskott på i genomsnitt ${surplus}/mån. Vi kontrollerar nuläget separat.`);
    const goalLine = planned
      ? T(`The goal needs ${need} a month, which is not enough alone — with the deficit the planned change is ${planned} a month.`, `Tavoitteelle ${need}/kk ei yksin riitä — alijäämä mukaan lukien muutos on ${planned}/kk.`, `Målet behöver ${need}/mån., vilket inte räcker ensamt — med underskottet är den planerade ändringen ${planned}/mån.`)
      : T('We start with everyday essentials and bills, not a savings challenge.', 'Aloitetaan arjen välttämättömistä menoista ja laskuista, ei säästöhaasteesta.', 'Vi börjar med vardagens nödvändiga utgifter och räkningar, inte med en sparutmaning.');
    const tight = rec.goal_reservations_present
      ? T(` The calculation includes ${fmt(rec.goal_contributions)} reserved for goals until payday.`, ` Laskelma sisältää tavoitevarauksia ${fmt(rec.goal_contributions)} palkkapäivään asti.`, ` Beräkningen inkluderar ${fmt(rec.goal_contributions)} reserverat för mål fram till lönedagen.`)
      : '';
    return {
      label: T('Checking your recovery picture…', 'Katsotaan tilannettasi…', 'Tittar på din återhämtning…'), tool: 'get_overview', args: {}, txCount: rec.tx_count,
      widgets: [wid('safe_to_spend', fixtureSafeToSpend(id, lang))],
      text: sisu
        ? T(`Heads up — this one needs your full focus. Your balance is **${balance}**. ${trend} ${goalLine}${tight} One small step today: list bills due before payday and check which are essential.`, `Huomio – tämä vaatii nyt täyden keskittymisen. Saldosi on **${balance}**. ${trend} ${goalLine}${tight} Yksi pieni askel tänään: listaa ennen palkkapäivää erääntyvät laskut ja tarkista, mitkä ovat välttämättömiä.`, `Obs – det här kräver fullfokus. Ditt saldo är **${balance}**. ${trend} ${goalLine}${tight} Ett litet steg i dag: lista räkningar som förfaller före lönedagen och kontrollera vilka som är nödvändiga.`)
        : T(`Let's look at this together. Your balance is **${balance}**. ${trend} ${goalLine}${tight} If it feels heavy, we can take one bill or essential at a time — where would you like to start?`, `Katsotaan tätä yhdessä. Saldosi on **${balance}**. ${trend} ${goalLine}${tight} Jos tilanne tuntuu raskaalta, voidaan ottaa yksi lasku tai meno kerrallaan — mistä haluaisit aloittaa?`, `Vi tittar på det här tillsammans. Ditt saldo är **${balance}**. ${trend} ${goalLine}${tight} Om det känns tungt kan vi ta en räkning eller en nödvändig utgift i taget — var vill du börja?`),
      mood: rec.state === 'ordinary' ? 'neutral' : 'concerned',
      suggestions: S3(['Where does the six-month spending gap come from?', 'How do I make it to payday?', 'What is an emergency buffer and how do I start one?'], ['Mistä kuuden kuukauden menoero muodostuu?', 'Miten selviän palkkapäivään asti?', 'Mikä on puskurirahasto ja miten aloitan sen?'], ['Var kommer utgiftsgapet på sex månader från?', 'Hur klarar jag mig till lönen?', 'Vad är en buffert och hur börjar jag en?']),
    };
  }

  if (has(q, ['six-month spending gap', 'kuuden kuukauden menoero', 'utgiftsgapet på sex månader', 'where does the deficit', 'mistä menoero', 'var kommer underskottet', 'deficit'])) {
    const start = addMonths(monthStart(AS_OF), -6);
    const end = addDays(monthStart(AS_OF), -1);
    const sp = fixtureSpending(id, { start, end, group_by: 'category' });
    const top = sp.groups[0];
    const income = fmt((rec.monthly_income ?? 0) * rec.months);
    const net = fmt(rec.monthly_surplus ?? 0);
    return {
      label: T('Looking for the six-month gap…', 'Etsin kuuden kuukauden menoeroa…', 'Letar efter gapet på sex månader…'), tool: 'query_spending', args: { start, end, group_by: 'category' }, txCount: sp.count,
      widgets: [wid('bar_chart', { title: `${start} – ${end}`, unit: '€', bars: sp.groups.map((g) => ({ label: g.label, value: g.total })) })],
      text: T(`Six full months: income ${income}, spending **${fmt(sp.total)}**. Average monthly net: **${net}**. Biggest spending group: ${top?.label ?? '—'}. Which costs could change without compromising essentials?`, `Kuusi täyttä kuukautta: tulot ${income}, menot **${fmt(sp.total)}**. Keskimääräinen erotus: **${net}/kk**. Suurin menoryhmä: ${top?.label ?? '—'}. Missä menoissa voisi joustaa vaarantamatta välttämättömiä tarpeita?`, `Sex hela månader: inkomster ${income}, utgifter **${fmt(sp.total)}**. Genomsnittligt netto: **${net}/mån.** Största utgiftsgrupp: ${top?.label ?? '—'}. Vilka utgifter kunde ändras utan att äventyra det nödvändiga?`),
      mood: 'concerned',
      suggestions: S3(['How do I get back to a positive balance?', 'How do I make it to payday?', 'Where can I cut back?'], ['Miten pääsen takaisin plussalle?', 'Miten selviän palkkapäivään asti?', 'Mistä voin karsia?'], ['Hur kommer jag tillbaka till plus?', 'Hur klarar jag mig till lönen?', 'Var kan jag dra ner?']),
    };
  }

  if (req.image_base64) {
    const sts = fixtureSafeToSpend(id, lang);
    fmtLocale = lang;
    const price = 79.9;
    const fits = price <= sts.safe_this_week;
    return {
      label: T('Reading your photo…', 'Luen kuvaa…', 'Läser bilden…'), tool: 'safe_to_spend', args: {}, txCount: 42,
      widgets: [wid('safe_to_spend', sts)],
      text: T(
        `In demo mode I can't read the photo (that needs the live AI), so let's assume the price is **${fmt(price)}**.\n\nThis week you can safely spend **${fmt(sts.safe_this_week)}**. ${fits ? 'It fits — but it takes a big bite of this week\'s room.' : 'It does not fit in this week\'s safe amount. Wait for payday or turn it into a goal.'}\n\n💡 Before buying, ask: which basket is this — a need, or a leak?`,
        `Demotilassa en pysty lukemaan kuvaa (se vaatii live-tekoälyn), joten oletetaan hinnaksi **${fmt(price)}**.\n\nTällä viikolla sinulla on käyttövaraa **${fmt(sts.safe_this_week)}**. ${fits ? 'Ostos mahtuu – mutta se vie ison osan viikon liikkumavarasta.' : 'Ostos ei mahdu tämän viikon käyttövaraan. Odota palkkapäivään tai tee siitä säästötavoite.'}\n\n💡 Kysy ennen ostosta: kumpaan koriin tämä kuuluu – tarpeisiin vai vuotoihin?`,
        `I demoläget kan jag inte läsa bilden (det kräver den riktiga AI:n), så vi antar att priset är **${fmt(price)}**.\n\nDen här veckan kan du tryggt använda **${fmt(sts.safe_this_week)}**. ${fits ? 'Köpet ryms – men det tar en stor del av veckans utrymme.' : 'Köpet ryms inte i veckans trygga summa. Vänta till lönen eller gör det till ett sparmål.'}\n\n💡 Fråga dig före köpet: vilken korg hör det här till – ett behov eller en läcka?`,
      ),
      mood: fits ? 'neutral' : 'concerned',
      suggestions: S3(['Make it a goal', 'What is safe to spend this week?', 'Where can I cut back?'], ['Tee tästä tavoite', 'Paljonko voin käyttää tällä viikolla?', 'Mistä voin karsia?'], ['Gör det till ett sparmål', 'Hur mycket kan jag tryggt använda den här veckan?', 'Var kan jag dra ner?']),
    };
  }

  if (has(q, ['taxi', 'taksi', 'uber', 'cab'])) {
    const taxiTx = generate(id).txs.filter((t) => t.mcc === 4121);
    const lastMonth = sumAbs(taxiTx.filter((t) => t.date >= prevMonthStart && t.date <= prevMonthEnd));
    const n = taxiTx.filter((t) => t.date >= prevMonthStart && t.date <= prevMonthEnd).length;
    const bars = Array.from({ length: 6 }, (_, i) => {
      const m = monthKey(addMonths(monthStart(AS_OF), i - 5));
      return { label: m, value: sumAbs(taxiTx.filter((t) => monthKey(t.date) === m)), highlight: m === monthKey(prevMonthStart) };
    });
    return {
      label: T('Checking your taxi rides…', 'Tarkistan taksimatkasi…', 'Kollar dina taxiresor…'), tool: 'query_spending', args: { mcc: 4121, group_by: 'month' }, txCount: taxiTx.length,
      widgets: [
        wid('kpi', { items: [{ label: T('Taxis last month', 'Taksit viime kuussa', 'Taxi förra månaden'), value: lastMonth, unit: '€', tone: lastMonth > 40 ? 'bad' : 'neutral' }, { label: T('Rides', 'Matkoja', 'Resor'), value: n, unit: '' }] }),
        wid('bar_chart', { title: T('Taxis per month', 'Taksit / kk', 'Taxi / mån'), unit: '€', bars }),
      ],
      text: sisu
        ? T(
            `Last month taxis took **${fmt(lastMonth)}** (${n} rides). That's your **leak basket** — an easy rep to train! 💪\n\nChallenge: swap half of those rides for transit for the next 2 weeks?\n\n💡 Leaks are choices, not must-pays.`,
            `Viime kuussa taksit veivät **${fmt(lastMonth)}** (${n} matkaa). Ne kuuluvat **vuotokoriin** – helppo treenikohde! 💪\n\nHaaste: puolet matkoista bussilla seuraavat kaksi viikkoa?\n\n💡 Vuodot ovat valintoja, eivät pakkoja.`,
            `Förra månaden gick **${fmt(lastMonth)}** till taxi (${n} resor). Det är din **läckkorg** – ett lätt träningspass! 💪\n\nUtmaning: åk kollektivt på hälften av resorna de närmaste två veckorna?\n\n💡 Läckor är val, inte måsten.`,
          )
        : T(
            `Last month you spent **${fmt(lastMonth)}** on taxis (${n} rides). They count as **everyday leaks** because they're choices.\n\nWhen does a taxi feel necessary to you — late nights, or when you're in a rush?\n\n💡 Knowing *why* you spend makes it easier to change *how*.`,
            `Viime kuussa käytit takseihin **${fmt(lastMonth)}** (${n} matkaa). Ne lasketaan **arjen vuotoihin**, koska ne ovat valintoja.\n\nMilloin taksi tuntuu sinusta välttämättömältä – myöhään illalla vai kiireessä?\n\n💡 Kun tiedät, *miksi* kulutat, on helpompi muuttaa sitä, *miten* kulutat.`,
            `Förra månaden lade du **${fmt(lastMonth)}** på taxi (${n} resor). De räknas som **vardagsläckor**, eftersom de är val.\n\nNär känns taxi nödvändig för dig – sent på kvällen eller när du har bråttom?\n\n💡 När du vet *varför* du spenderar är det lättare att ändra *hur*.`,
          ),
      mood: lastMonth > 40 ? 'concerned' : 'neutral',
      suggestions: S3(['What if I cut taxis by 50%?', 'Show all my transport costs', 'What kind of spender am I?'], ['Entä jos puolittaisin taksit?', 'Näytä kaikki liikkumiskulut', 'Millainen kuluttaja olen?'], ['Tänk om jag halverar taxiresorna?', 'Visa alla mina resekostnader', 'Hurdan konsument är jag?']),
    };
  }

  if (has(q, ['spender', 'kuluttaja', 'konsument', 'hurdan', 'profil', 'personality', 'what kind'])) {
    const prof = fixtureProfile(id, lang);
    const leakPct = Math.round(prof.leak_share * 100);
    const target = Math.max(15, leakPct - 10);
    return {
      label: T('Analysing your spending style…', 'Analysoin kulutustyyliäsi…', 'Analyserar din konsumtionsstil…'), tool: 'spender_profile', args: {}, txCount: 214,
      widgets: [wid('spender_profile', prof)],
      text: sisu
        ? T(
            `You're a **${prof.archetype.name}** ${prof.archetype.emoji}! ${prof.archetype.description}\n\nYour leak basket is ${pc(leakPct)} of spending. Let's train it under ${pc(target)}!\n\n💡 A spending style isn't a verdict — it's a starting line.`,
            `Olet **${prof.archetype.name}** ${prof.archetype.emoji}! ${prof.archetype.description}\n\nVuotokori on ${pc(leakPct)} kulutuksestasi. Treenataan se alle ${pc(target)}:n!\n\n💡 Kulutustyyli ei ole tuomio – se on lähtöviiva.`,
            `Du är **${prof.archetype.name}** ${prof.archetype.emoji}! ${prof.archetype.description}\n\nLäckkorgen är ${pc(leakPct)} av dina utgifter. Vi tränar ner den under ${pc(target)}!\n\n💡 En konsumtionsstil är ingen dom – den är en startlinje.`,
          )
        : T(
            `Your style is **${prof.archetype.name}** ${prof.archetype.emoji}. ${prof.archetype.description}\n\nYour savings rate is ${pc(Math.round(prof.savings_rate * 100))} and ${pc(Math.round(prof.weekend_share * 100))} of spending happens Fri–Sun. Does that sound like you?\n\n💡 Habits show up in data before we notice them ourselves.`,
            `Kulutustyylisi on **${prof.archetype.name}** ${prof.archetype.emoji}. ${prof.archetype.description}\n\nSäästöasteesi on ${pc(Math.round(prof.savings_rate * 100))}, ja viikonloppujen osuus kulutuksesta on ${pc(Math.round(prof.weekend_share * 100))}. Tunnistatko itsesi?\n\n💡 Tavat näkyvät datassa ennen kuin huomaamme ne itse.`,
            `Din stil är **${prof.archetype.name}** ${prof.archetype.emoji}. ${prof.archetype.description}\n\nDin sparkvot är ${pc(Math.round(prof.savings_rate * 100))} och ${pc(Math.round(prof.weekend_share * 100))} av utgifterna sker fre–sön. Känner du igen dig?\n\n💡 Vanor syns i datan innan vi själva märker dem.`,
          ),
      mood: prof.archetype.key === 'squirrel_saver' || prof.archetype.key === 'steady_planner' ? 'happy' : 'neutral',
      suggestions: S3(['How do I compare to my peers?', 'Where do my leaks go?', 'Give me a 7-day challenge'], ['Miten vertaudun ikätovereihini?', 'Mihin vuotoni menevät?', 'Anna 7 päivän haaste'], ['Hur ligger jag till jämfört med jämnåriga?', 'Vart går mina läckor?', 'Ge mig en 7-dagarsutmaning']),
    };
  }

  if (has(q, ['what if', 'entä jos', 'tänk om', 'reduce', 'vähentä', 'minska', 'cut', 'karsi', 'dra ner', 'dining', 'ravintol', 'restaurang', 'eating out', 'ulkona', 'äta ute', 'åt ute'])) {
    const pct = Number(/(\d{1,3})\s*%/.exec(q)?.[1] ?? 20);
    const category = has(q, ['taxi', 'taksi']) ? 'Transportation' : 'Restaurants';
    const result = fixtureWhatIf(id, { adjustments: [{ category, change_pct: -pct }], horizon_months: 12 });
    const effect = (rec.monthly_surplus ?? 0) < 0
      ? T('This helps close the gap before saving.', 'Tämä auttaa kuromaan vajetta umpeen ennen säästämistä.', 'Det hjälper till att täppa till underskottet före sparandet.')
      : T('This can help bring the negative balance towards zero before saving.', 'Tämä voi auttaa nostamaan miinussaldoa kohti nollaa ennen säästämistä.', 'Det kan hjälpa det negativa saldot mot noll före sparandet.');
    return {
      label: T('Simulating your savings…', 'Lasken säästöpotentiaalia…', 'Räknar på sparpotentialen…'), tool: 'simulate_what_if', args: { category, change_pct: -pct }, txCount: 88,
      widgets: [wid('what_if', { base_adjustments: [{ category, change_pct: -pct }], result, slider: { category, min: -100, max: 0, value: -pct } })],
      text: recovering ? T(`A ${pc(pct)} reduction frees **${fmt(result.monthly_saving)}/month**. ${effect}`, `${pc(pct)}:n vähennys vapauttaa **${fmt(result.monthly_saving)}/kk**. ${effect}`, `En minskning på ${pc(pct)} frigör **${fmt(result.monthly_saving)}/mån**. ${effect}`) : sisu
        ? T(
            `Cutting ${pc(pct)} frees **${fmt(result.monthly_saving)}/month** — that's **${fmt(result.total_saving)}** in a year! 🔥 Drag the slider to see more reps.\n\n💡 Small reps, big gains.`,
            `${pc(pct)}:n leikkaus vapauttaa **${fmt(result.monthly_saving)}/kk** – vuodessa **${fmt(result.total_saving)}**! 🔥 Liu'uta säädintä ja katso lisää.\n\n💡 Pienet toistot, isot tulokset.`,
            `Att dra ner ${pc(pct)} frigör **${fmt(result.monthly_saving)}/mån** – det blir **${fmt(result.total_saving)}** på ett år! 🔥 Dra i reglaget och se mer.\n\n💡 Små repetitioner, stora resultat.`,
          )
        : T(
            `If you reduce it by ${pc(pct)}, you'd save about **${fmt(result.monthly_saving)} a month** and **${fmt(result.total_saving)} a year**. Try the slider — what level would feel realistic to you?\n\n💡 A sustainable change is one you don't feel every day.`,
            `Jos vähennät ${pc(pct)}, säästät noin **${fmt(result.monthly_saving)} kuukaudessa** ja **${fmt(result.total_saving)} vuodessa**. Kokeile säädintä – mikä taso tuntuisi sinusta realistiselta?\n\n💡 Kestävä muutos on sellainen, jota et huomaa joka päivä.`,
            `Om du minskar med ${pc(pct)} sparar du ungefär **${fmt(result.monthly_saving)} i månaden** och **${fmt(result.total_saving)} om året**. Testa reglaget – vilken nivå skulle kännas realistisk för dig?\n\n💡 En hållbar förändring är en som du inte känner av varje dag.`,
          ),
      mood: recovering ? 'concerned' : 'happy',
      suggestions: recovering ? recoverySuggestions : S3(['Put the savings towards a goal', 'What else is in my leak basket?', 'Help me save for a car that costs 12000'], ['Ohjaa säästö tavoitteeseen', 'Mitä muuta vuotokorissani on?', 'Auta minua säästämään 12000 euron autoon'], ['Lägg besparingen på ett sparmål', 'Vad finns mer i min läckkorg?', 'Hjälp mig spara till en bil som kostar 12000 euro']),
    };
  }

  if (has(q, ['save for', 'säästä', 'säästää', 'spara till', 'sparmål', 'goal', 'tavoite', 'laptop', 'trip', 'matka', 'resa', 'faster', 'nopeammin', 'snabbare', 'förläng']) || /\b(car|bil|auto)\b/.test(q)) {
    const goals = fixtureGoals(id, lang);
    const namesById = new Map<string, string[]>();
    for (const l of ['en', 'fi', 'sv'] as Locale[])
      for (const g of fixtureGoals(id, l))
        namesById.set(g.id, [...(namesById.get(g.id) ?? []), g.name.toLowerCase()]);
    const existing = goals.find((g) => (namesById.get(g.id) ?? []).some((n) => q.includes(n)));
    const target = existing?.target_amount ?? Number(/(\d[\d\s]{2,})/.exec(q)?.[1]?.replace(/\s/g, '') ?? 12000);
    const isCar = /\b(car|bil|auto)\b/.test(q);
    const goalName = existing?.name ?? (isCar ? T('Car', 'Auto', 'Bil') : T('New goal', 'Uusi tavoite', 'Nytt sparmål'));
    const deadline = existing?.deadline ?? addMonths(AS_OF, 18);
    const plan = fixturePlanGoal(id, { target_amount: target, name: goalName, deadline, saved_amount: existing?.saved_amount ?? 0 }, lang);
    return {
      label: T('Building your savings plan…', 'Laadin säästösuunnitelmaa…', 'Gör upp en sparplan…'), tool: 'plan_goal', args: { target_amount: target }, txCount: 156,
      widgets: [
        wid('goal_plan', plan),
        wid('action_buttons', { buttons: [{ label: T('Show my leak basket', 'Näytä vuotokorini', 'Visa min läckkorg'), kind: 'prompt', payload: T('Where do my leaks go?', 'Mihin vuotoni menevät?', 'Vart går mina läckor?') }, { label: T('Open my goals', 'Avaa tavoitteet', 'Öppna sparmålen'), kind: 'open_tab', payload: 'goals' }] }),
      ],
      text: recovering || plan.feasibility === 'unrealistic' ? `${goalName}: ${fmt(target)}. ${plan.summary} ${essentials}` : sisu
        ? T(
            `${fmt(target)} in ${plan.months} months = **${fmt(plan.needed_per_month)}/month**. ${plan.summary}\n\nYour training plan is below. Shall we lock it in? 🤝\n\n💡 A goal without an amount and a date is just a wish.`,
            `${fmt(target)} ${plan.months} kuukaudessa = **${fmt(plan.needed_per_month)}/kk**. ${plan.summary}\n\nTreeniohjelma on valmiina alla. Lyödäänkö lukkoon? 🤝\n\n💡 Tavoite ilman summaa ja päivämäärää on vain toive.`,
            `${fmt(target)} på ${plan.months} månader = **${fmt(plan.needed_per_month)}/mån**. ${plan.summary}\n\nTräningsprogrammet finns här nedan. Ska vi slå fast det? 🤝\n\n💡 Ett mål utan summa och datum är bara en önskan.`,
          )
        : T(
            `${plan.summary}\n\nBelow is where the money could come from — mostly the leak basket, so your essentials stay untouched. Which of these feels easiest?\n\n💡 Split a big goal into monthly instalments — then it's just one more bill to yourself.`,
            `${plan.summary}\n\nAlla on ehdotus siitä, mistä summa voisi löytyä – pääosin vuotokorista, jotta välttämättömät menot pysyvät ennallaan. Mikä näistä tuntuu helpoimmalta?\n\n💡 Pilko iso tavoite kuukausieriin – silloin se on vain yksi lasku muiden joukossa, itsellesi.`,
            `${plan.summary}\n\nHär nedan ser du varifrån pengarna kunde komma – mest från läckkorgen, så att de nödvändiga utgifterna förblir orörda. Vilket av förslagen känns lättast?\n\n💡 Dela upp ett stort mål i månadsposter – då är det bara en räkning bland andra, till dig själv.`,
          ),
      mood: plan.feasibility === 'unrealistic' ? 'concerned' : 'happy',
      suggestions: S3(['What if I extend the deadline?', 'Where do my leaks go?', 'What is safe to spend this week?'], ['Entä jos pidennän aikaa?', 'Mihin vuotoni menevät?', 'Paljonko voin käyttää tällä viikolla?'], ['Tänk om jag förlänger tiden?', 'Vart går mina läckor?', 'Hur mycket kan jag tryggt använda den här veckan?']),
    };
  }

  if (has(q, ['survive', 'selviä', 'selviän', 'payday', 'palkkapäiv', 'make it', 'until', 'klara', 'lönen', 'lönedag'])) {
    const amount = Number(/(\d{2,5})\s*(€|eur|euro)/.exec(q)?.[1] ?? NaN);
    const plan = fixtureSurvival(id, Number.isFinite(amount) ? amount : undefined, undefined, lang);
    return {
      label: T('Building your survival plan…', 'Laadin selviytymissuunnitelmaa…', 'Gör upp en överlevnadsplan…'), tool: 'survival_plan', args: Number.isFinite(amount) ? { amount } : {}, txCount: 64,
      widgets: [wid('survival_plan', plan)],
      text: recovering ? T(`For ${plan.days} days, after listed bills: **${fmt(plan.free_money)}** (${fmt(plan.per_day)}/day). ${essentials}`, `${plan.days} päiväksi jää listattujen laskujen jälkeen **${fmt(plan.free_money)}** (${fmt(plan.per_day)}/päivä). ${essentials}`, `För ${plan.days} dagar återstår efter listade räkningar **${fmt(plan.free_money)}** (${fmt(plan.per_day)}/dag). ${essentials}`) : sisu
        ? T(
            `${plan.days} days, ${fmt(plan.amount)}. After bills you have **${fmt(plan.free_money)}** = **${fmt(plan.per_day)}/day**. ${plan.risk === 'short' ? 'Tough session — but we do this together!' : 'You can do this! 💪'}\n\n💡 A daily budget is easier to keep than a monthly one.`,
            `${plan.days} päivää, ${fmt(plan.amount)}. Laskujen jälkeen jää **${fmt(plan.free_money)}** = **${fmt(plan.per_day)}/päivä**. ${plan.risk === 'short' ? 'Tiukka treeni – mutta tehdään tämä yhdessä!' : 'Pystyt tähän! 💪'}\n\n💡 Päiväbudjetti on helpompi pitää kuin kuukausibudjetti.`,
            `${plan.days} dagar, ${fmt(plan.amount)}. Efter räkningarna har du **${fmt(plan.free_money)}** = **${fmt(plan.per_day)}/dag**. ${plan.risk === 'short' ? 'Ett tufft pass – men vi gör det tillsammans!' : 'Du klarar det här! 💪'}\n\n💡 En dagsbudget är lättare att hålla än en månadsbudget.`,
          )
        : T(
            `You have ${fmt(plan.amount)} for ${plan.days} days. Once bills (${fmt(plan.upcoming_bills_total)}) are covered, that leaves **${fmt(plan.per_day)} a day**. Below is a suggested split.\n\nWhich of these tips would fit your days best?\n\n💡 Pay bills first, then divide the rest by days.`,
            `Sinulla on ${fmt(plan.amount)} ${plan.days} päiväksi. Kun laskut (${fmt(plan.upcoming_bills_total)}) on maksettu, jää **${fmt(plan.per_day)} päivässä**. Alla on ehdotus jaosta.\n\nMikä näistä vinkeistä sopisi arkeesi parhaiten?\n\n💡 Maksa laskut ensin ja jaa loput päiville.`,
            `Du har ${fmt(plan.amount)} för ${plan.days} dagar. När räkningarna (${fmt(plan.upcoming_bills_total)}) är betalda blir det **${fmt(plan.per_day)} per dag**. Här nedan finns ett förslag på fördelning.\n\nVilket av tipsen skulle passa din vardag bäst?\n\n💡 Betala räkningarna först och dela resten på dagarna.`,
          ),
      mood: plan.risk === 'ok' ? 'happy' : 'concerned',
      suggestions: S3(['Which subscriptions can I pause?', 'What is safe to spend this week?', 'Teach me about emergency funds'], ['Mitkä tilaukset voin tauottaa?', 'Paljonko voin käyttää tällä viikolla?', 'Opeta minulle puskurirahastosta'], ['Vilka prenumerationer kan jag pausa?', 'Hur mycket kan jag tryggt använda den här veckan?', 'Lär mig om buffertar']),
    };
  }

  if (has(q, ['safe', 'turvall', 'afford', 'varaa', 'paljonko voin käyttää', 'hur mycket kan jag använda', 'this week', 'tällä viikolla', 'can i spend', 'voinko', 'tryggt', 'har jag råd', 'den här veckan'])) {
    const sts = fixtureSafeToSpend(id, lang);
    return {
      label: T('Working out what is safe…', 'Lasken käyttövaraasi…', 'Räknar ut en trygg summa…'), tool: 'safe_to_spend', args: {}, txCount: 37,
      widgets: [wid('safe_to_spend', sts)],
      text: recovering ? T(`Calculated spending room: **${fmt(sts.safe_this_week)}** this week (${fmt(sts.safe_per_day)}/day). ${essentials}`, `Laskennallinen käyttövara: **${fmt(sts.safe_this_week)}** tällä viikolla (${fmt(sts.safe_per_day)}/päivä). ${essentials}`, `Beräknat utrymme: **${fmt(sts.safe_this_week)}** denna vecka (${fmt(sts.safe_per_day)}/dag). ${essentials}`) : sisu
        ? T(
            `This week you can safely spend **${fmt(sts.safe_this_week)}** — that's **${fmt(sts.safe_per_day)}/day**. ${sts.days_until_payday} days to payday. ${sts.status === 'comfortable' ? 'Strong position, hold the line! 🏆' : "It's tight — stay disciplined! 💪"}\n\n💡 Your balance isn't the same as money you can spend.`,
            `Tällä viikolla käyttövaraa on **${fmt(sts.safe_this_week)}** – eli **${fmt(sts.safe_per_day)}/päivä**. Palkkapäivään ${sts.days_until_payday} päivää. ${sts.status === 'comfortable' ? 'Hyvä tilanne, pidä linja! 🏆' : 'Tiukkaa – pidetään kuri! 💪'}\n\n💡 Saldo ei ole sama asia kuin käytettävissä oleva raha.`,
            `Den här veckan kan du tryggt använda **${fmt(sts.safe_this_week)}** – alltså **${fmt(sts.safe_per_day)}/dag**. ${sts.days_until_payday} dagar till lönen. ${sts.status === 'comfortable' ? 'Bra läge, håll linjen! 🏆' : 'Det är stramt – håll disciplinen! 💪'}\n\n💡 Saldot är inte samma sak som pengar du kan använda.`,
          )
        : T(
            `This week you can safely spend **${fmt(sts.safe_this_week)}** (${fmt(sts.safe_per_day)}/day). ${sts.explanation}\n\nDoes that feel realistic for your week?\n\n💡 Part of your balance already belongs to upcoming bills.`,
            `Tällä viikolla voit huoletta käyttää **${fmt(sts.safe_this_week)}** (${fmt(sts.safe_per_day)}/päivä). ${sts.explanation}\n\nTuntuuko summa realistiselta arkeesi?\n\n💡 Osa saldosta kuuluu jo tuleville laskuille.`,
            `Den här veckan kan du tryggt använda **${fmt(sts.safe_this_week)}** (${fmt(sts.safe_per_day)}/dag). ${sts.explanation}\n\nKänns summan realistisk för din vecka?\n\n💡 En del av saldot hör redan till kommande räkningar.`,
          ),
      mood: sts.status === 'comfortable' ? 'happy' : 'concerned',
      suggestions: S3(['How do I make it to payday?', 'Where do my leaks go?', 'Show my upcoming bills'], ['Miten selviän palkkapäivään?', 'Mihin vuotoni menevät?', 'Näytä tulevat laskut'], ['Hur klarar jag mig till lönen?', 'Vart går mina läckor?', 'Visa mina kommande räkningar']),
    };
  }

  if (has(q, ['home', 'asunto', 'mortgage', 'laina', 'house', 'koti', 'bostad', 'bolån', 'egen insats'])) {
    const hr = fixtureHomeReadiness(id, undefined, lang);
    return {
      label: T('Checking your home readiness…', 'Arvioin valmiuttasi asunnon ostoon…', 'Bedömer om du är redo för bostadsköp…'), tool: 'home_readiness', args: {}, txCount: 312,
      widgets: [wid('home_readiness', hr)],
      text: T(
        `For a ${fmt(hr.property_price)} home you'd need about **${fmt(hr.equity_needed)}** down payment. I estimate you have **${fmt(hr.your_equity_estimate)}**.\n\n${hr.gaps.length ? `To work on: ${hr.gaps.join(' ')}` : 'Looking good!'}\n\nS-Bank's mortgage advisors can help with the next step.\n\n💡 A steady savings history weighs as much as the lump sum.`,
        `${fmt(hr.property_price)} asuntoon tarvitset noin **${fmt(hr.equity_needed)}** omarahoitusta. Arvioni mukaan sinulla on **${fmt(hr.your_equity_estimate)}**.\n\n${hr.gaps.length ? `Kehityskohteet: ${hr.gaps.join(' ')}` : 'Näyttää hyvältä!'}\n\nS-Pankin asuntolainaneuvojat auttavat seuraavassa askeleessa.\n\n💡 Säännöllinen säästöhistoria painaa yhtä paljon kuin summa.`,
        `För en bostad för ${fmt(hr.property_price)} behöver du cirka **${fmt(hr.equity_needed)}** i egen insats. Enligt min uppskattning har du **${fmt(hr.your_equity_estimate)}**.\n\n${hr.gaps.length ? `Att jobba på: ${hr.gaps.join(' ')}` : 'Det ser bra ut!'}\n\nS-Bankens bolånerådgivare hjälper dig med nästa steg.\n\n💡 En jämn sparhistorik väger lika tungt som summan.`,
      ),
      mood: hr.verdict === 'ready' ? 'celebrate' : 'neutral',
      suggestions: S3(['Make a down-payment savings plan', 'Teach me about mortgages', 'What if I cut leaks by 30%?'], ['Tee omarahoitussuunnitelma', 'Opeta minulle asuntolainasta', 'Entä jos karsin vuotoja 30 %?'], ['Gör en sparplan för egen insats', 'Lär mig om bolån', 'Tänk om jag minskar läckorna med 30 %?']),
    };
  }

  if (has(q, ['subscription', 'tilaus', 'tilauk', 'recurring', 'toistuv', 'bills', 'laskut', 'prenumeration', 'återkommande', 'räkning'])) {
    const rec = fixtureRecurring(id);
    return {
      label: T('Finding recurring payments…', 'Etsin toistuvat maksut…', 'Letar efter återkommande betalningar…'), tool: 'recurring_payments', args: {}, txCount: rec.items.length * 9,
      widgets: [wid('bar_chart', { title: T('Recurring per month', 'Toistuvat maksut / kk', 'Återkommande / mån'), unit: '€', bars: rec.items.map((r) => ({ label: r.label, value: r.avg_amount, highlight: r.category === 'Entertainment' })) })],
      text: T(
        `I found **${rec.items.length} recurring payments**, **${fmt(rec.monthly_total)}/month** in total. They're fixed basket — but ones you chose.\n\n${sisu ? 'Challenge: pause one streaming service this month! 💪' : 'Which of these did you actually use last month?'}\n\n💡 Rotating subscriptions saves money without giving anything up.`,
        `Löysin **${rec.items.length} toistuvaa maksua**, yhteensä **${fmt(rec.monthly_total)}/kk**. Ne kuuluvat kiinteään koriin – mutta olet valinnut ne itse.\n\n${sisu ? 'Haaste: tauota yksi suoratoistopalvelu tässä kuussa! 💪' : 'Mitä näistä oikeasti käytit viime kuussa?'}\n\n💡 Tilausten vuorottelu säästää rahaa ilman, että joudut luopumaan mistään.`,
        `Jag hittade **${rec.items.length} återkommande betalningar**, sammanlagt **${fmt(rec.monthly_total)}/mån**. De hör till den fasta korgen – men du har valt dem själv.\n\n${sisu ? 'Utmaning: pausa en streamingtjänst den här månaden! 💪' : 'Vilka av dem använde du faktiskt förra månaden?'}\n\n💡 Att rotera prenumerationer sparar pengar utan att du behöver avstå från något.`,
      ),
      mood: 'neutral',
      suggestions: S3(['What if I cancel one streaming service?', 'What is safe to spend this week?', 'Where do my leaks go?'], ['Entä jos peruisin yhden suoratoistopalvelun?', 'Paljonko voin käyttää tällä viikolla?', 'Mihin vuotoni menevät?'], ['Tänk om jag säger upp en streamingtjänst?', 'Hur mycket kan jag tryggt använda den här veckan?', 'Vart går mina läckor?']),
    };
  }

  if (has(q, ['peer', 'compare', 'vertaa', 'ikätov', 'average', 'keskiver', 'benchmark', 'jämnårig', 'jämför'])) {
    const b = fixtureBenchmarks(id);
    const top = [...b.categories].sort((a, c) => c.percentile - a.percentile)[0];
    return {
      label: T('Comparing with your peers…', 'Vertaan ikätovereihisi…', 'Jämför med dina jämnåriga…'), tool: 'benchmarks', args: {}, txCount: 214,
      widgets: [wid('benchmark', b)],
      text: T(
        `Compared with "${b.peer_group.label}" (${b.peer_group.size} people), your biggest difference is **${top.category}**: you spend ${fmt(top.you_monthly)}/month vs a median of ${fmt(top.peer_median_monthly)}.\n\n💡 Benchmarks show what's "normal" — but your own goals decide what's right.`,
        `Verrattuna ryhmään ”${b.peer_group.label}” (${b.peer_group.size} henkilöä) suurin ero on luokassa **${top.category}**: käytät ${fmt(top.you_monthly)}/kk, kun mediaani on ${fmt(top.peer_median_monthly)}.\n\n💡 Vertailu näyttää, mikä on ”tavallista” – mutta omat tavoitteesi ratkaisevat, mikä on sinulle oikein.`,
        `Jämfört med gruppen ”${b.peer_group.label}” (${b.peer_group.size} personer) är din största skillnad i kategorin **${top.category}**: du lägger ${fmt(top.you_monthly)}/mån mot medianen ${fmt(top.peer_median_monthly)}.\n\n💡 Jämförelser visar vad som är ”normalt” – men dina egna mål avgör vad som är rätt för dig.`,
      ),
      mood: top.percentile > 75 ? 'concerned' : 'happy',
      suggestions: S3([`What if I cut ${top.category} by 20%?`, 'What kind of spender am I?', 'Where do my leaks go?'], [`Entä jos vähennän luokkaa ${top.category} 20 %?`, 'Millainen kuluttaja olen?', 'Mihin vuotoni menevät?'], [`Tänk om jag minskar ${top.category} med 20 %?`, 'Hurdan konsument är jag?', 'Vart går mina läckor?']),
    };
  }

  if (has(q, ['learn', 'teach', 'opeta', 'explain', 'selitä', 'what is', 'mikä on', 'emergency', 'puskuri', 'compound', 'korkoa', 'lär mig', 'förklara', 'vad är', 'buffert', 'ränta', 'lektion'])) {
    const lessons = fixtureLessons(lang);
    const l = has(q, ['emergency', 'puskuri', 'buffert']) ? lessons[2] : has(q, ['compound', 'korkoa', 'invest', 'sijoit', 'ränta']) ? lessons[5] : has(q, ['mortgage', 'asuntolaina', 'bolån']) ? lessons[7] : lessons[0];
    return {
      label: T('Fetching a lesson…', 'Haen oppitunnin…', 'Hämtar en lektion…'), tool: 'explain_concept', args: { topic: l.id }, txCount: 0,
      widgets: [wid('lesson', { id: l.id, title: l.title, body: l.body, emoji: l.emoji, quiz: l.quiz ?? undefined })],
      text: T(`Here's a quick lesson: **${l.title}** ${l.emoji}. Test yourself with the quiz at the end!`, `Tässä lyhyt oppitunti: **${l.title}** ${l.emoji}. Testaa osaamisesi lopun visalla!`, `Här är en kort lektion: **${l.title}** ${l.emoji}. Testa dig själv med quizet i slutet!`),
      mood: 'happy',
      suggestions: S3(['How does this apply to me?', 'Give me another lesson', 'What kind of spender am I?'], ['Miten tämä koskee minua?', 'Anna toinen oppitunti', 'Millainen kuluttaja olen?'], ['Hur gäller det här mig?', 'Ge mig en annan lektion', 'Hurdan konsument är jag?']),
    };
  }

  if (has(q, ['balance', 'saldo', 'how much do i have', 'paljonko minulla', 'hur mycket har jag'])) {
    const ov = fixtureOverview(id, lang);
    fmtLocale = lang;
    const [y, m, d] = AS_OF.split('-').map(Number);
    const asOf = lang === 'en' ? AS_OF : `${d}.${m}.${y}`;
    return {
      label: T('Fetching your balance…', 'Haen saldosi…', 'Hämtar ditt saldo…'), tool: 'get_balance', args: {}, txCount: 30,
      widgets: [
        wid('kpi', { items: [{ label: T('Balance', 'Saldo', 'Saldo'), value: ov.balance, unit: '€' }, { label: T('Income (mo)', 'Tulot (kk)', 'Inkomster (mån)'), value: ov.month.income, unit: '€', tone: 'good' }, { label: T('Spent (mo)', 'Menot (kk)', 'Utgifter (mån)'), value: ov.month.spent, unit: '€' }] }),
        wid('line_chart', { title: T('Balance, 30 days', 'Saldo 30 pv', 'Saldo, 30 dagar'), unit: '€', points: ov.trend_30d.map((pt) => ({ x: pt.date.slice(5), y: pt.balance })) }),
      ],
      text: T(
        `Your balance is **${fmt(ov.balance)}** (as of ${asOf}). This month: ${fmt(ov.month.income)} in, ${fmt(ov.month.spent)} out.\n\n💡 Watch the *direction* of your balance, not just the number.`,
        `Saldosi on **${fmt(ov.balance)}** (${asOf}). Tässä kuussa tuloja on tullut ${fmt(ov.month.income)} ja menoja ${fmt(ov.month.spent)}.\n\n💡 Seuraa saldon *suuntaa*, älä pelkkää lukua.`,
        `Ditt saldo är **${fmt(ov.balance)}** (${asOf}). Den här månaden: ${fmt(ov.month.income)} in och ${fmt(ov.month.spent)} ut.\n\n💡 Titta på saldots *riktning*, inte bara siffran.`,
      ),
      mood: 'neutral',
      suggestions: S3(['What is safe to spend this week?', 'Where does my money go?', 'What kind of spender am I?'], ['Paljonko voin käyttää tällä viikolla?', 'Mihin rahani menevät?', 'Millainen kuluttaja olen?'], ['Hur mycket kan jag tryggt använda den här veckan?', 'Vart går mina pengar?', 'Hurdan konsument är jag?']),
    };
  }

  // Default: where does my money go → three baskets.
  const b = fixtureBaskets(id, 6, lang);
  const cm = b.current_month;
  const total = cm.fixed + cm.irregular + cm.leak || 1;
  const leakPct = Math.round((cm.leak / total) * 100);
  return {
    label: T('Sorting your spending into baskets…', 'Jaan kulutuksesi koreihin…', 'Sorterar dina utgifter i korgar…'), tool: 'get_baskets', args: { months: 6 }, txCount: 96,
    widgets: [wid('basket_breakdown', { month: cm.month, fixed: cm.fixed, irregular: cm.irregular, leak: cm.leak, explanations: b.explanations, top: cm.top })],
    text: sisu
      ? T(
          `Hey ${name}! This month so far: fixed **${fmt(cm.fixed)}**, irregular **${fmt(cm.irregular)}**, leaks **${fmt(cm.leak)}** (${pc(leakPct)}).\n\nThe leak basket is your gym — that's where the gains are! 💪\n\n💡 Plan the fixed, save for the irregular, steer the leaks.`,
          `Hei ${name}! Tämän kuun kulutus tähän mennessä: kiinteät **${fmt(cm.fixed)}**, epäsäännölliset **${fmt(cm.irregular)}**, vuodot **${fmt(cm.leak)}** (${pc(leakPct)}).\n\nVuotokori on treenisalisi – siellä tulokset syntyvät! 💪\n\n💡 Kiinteät suunnitellaan, epäsäännöllisiin säästetään, vuotoja ohjataan.`,
          `Hej ${name}! Månadens utgifter hittills: fasta **${fmt(cm.fixed)}**, oregelbundna **${fmt(cm.irregular)}**, läckor **${fmt(cm.leak)}** (${pc(leakPct)}).\n\nLäckkorgen är ditt gym – det är där resultaten kommer! 💪\n\n💡 Planera de fasta, spara till de oregelbundna, styr läckorna.`,
        )
      : T(
          `Hi ${name}. This month your money splits into three baskets: fixed **${fmt(cm.fixed)}**, irregular **${fmt(cm.irregular)}** and everyday leaks **${fmt(cm.leak)}** (${pc(leakPct)}).\n\nDoes any of these surprise you?\n\n💡 The three baskets separate must-pays from choices.`,
          `Hei ${name}. Tämän kuun rahasi jakautuvat kolmeen koriin: kiinteät **${fmt(cm.fixed)}**, epäsäännölliset **${fmt(cm.irregular)}** ja arjen vuodot **${fmt(cm.leak)}** (${pc(leakPct)}).\n\nYllättikö jokin näistä?\n\n💡 Kolme koria auttaa erottamaan pakolliset menot valinnoista.`,
          `Hej ${name}. Den här månaden fördelar sig dina pengar på tre korgar: fasta **${fmt(cm.fixed)}**, oregelbundna **${fmt(cm.irregular)}** och vardagsläckor **${fmt(cm.leak)}** (${pc(leakPct)}).\n\nÖverraskade någon av dem dig?\n\n💡 De tre korgarna skiljer det du måste betala från det du själv väljer.`,
        ),
    mood: leakPct > 35 ? 'concerned' : 'happy',
    suggestions: S3(['How much could I save if I reduced dining out by 20%?', 'What is safe for me to spend this week?', 'What kind of spender am I?'], ['Paljonko säästäisin, jos söisin ulkona 20 % vähemmän?', 'Paljonko voin huoletta käyttää tällä viikolla?', 'Millainen kuluttaja olen?'], ['Hur mycket skulle jag spara om jag åt ute 20 % mindre?', 'Hur mycket kan jag tryggt använda den här veckan?', 'Hurdan konsument är jag?']),
  };
}

const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/**
 * Replays a realistic SSE conversation turn. Timings imitate a real model:
 * think → call a tool → emit widgets → stream tokens → done.
 */
export async function* fixtureChatStream(req: ChatRequest, signal?: AbortSignal): AsyncGenerator<SseEvent> {
  const lang = replyLocale(req);
  const plan = planChat(req);
  const aborted = () => signal?.aborted ?? false;
  yield { event: 'status', data: { state: 'thinking', label: tr(lang, 'Thinking…', 'Mietin…', 'Tänker…') } };
  await sleep(550);
  if (aborted()) return;
  yield { event: 'status', data: { state: 'tool', label: plan.label } };
  await sleep(700);
  if (aborted()) return;
  yield { event: 'tool', data: { name: plan.tool, args: plan.args, summary: plan.label.replace('…', '') } };
  for (const w of plan.widgets) {
    yield { event: 'widget', data: w };
    await sleep(120);
  }
  yield { event: 'status', data: { state: 'writing', label: tr(lang, 'Writing…', 'Kirjoitan…', 'Skriver…') } };
  const parts = plan.text.match(/\S+\s*/g) ?? [plan.text];
  for (const p of parts) {
    if (aborted()) return;
    yield { event: 'token', data: { text: p } };
    await sleep(18 + Math.random() * 26);
  }
  yield {
    event: 'done',
    data: {
      message_id: `m-${Date.now().toString(36)}`,
      sources: { tx_count: plan.txCount, period: tr(lang, 'Jan–Sep 2026', 'tammi–syys 2026', 'jan–sep 2026'), tools: [plan.tool] },
      suggestions: plan.suggestions,
      mood: plan.mood,
    },
  };
}
