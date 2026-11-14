# Rahakamu backend

FastAPI + DuckDB analytics engine and REST API for **Rahakamu**, the Personal Economic
Trainer. Every number the app or the AI coach shows comes from the functions described
here, computed from the customer's own transactions.

Supply your own authorised challenge files in the repository's `data/` directory before
starting the backend; see [Data sources](../docs/DATA_SOURCES.md). Challenge data, caches
and secrets are not included. The mobile offline demo does not need these files.

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000   # http://localhost:8000/docs
uv run pytest -q                                   # backend suite, ~35 s
```

The first start builds a read-only DuckDB cache from `data/transactions.parquet`
(~8 s, stored in `backend/.cache/`, rebuilt automatically when the data, `AS_OF_DATE` or
the basket rules change). Later starts and test runs attach it instantly.

## Configuration (`../.env` or environment)

| Variable | Default | Meaning |
|---|---|---|
| `AS_OF_DATE` | `2026-09-18` | The simulated "today". Nothing after it is ever read. |
| `DATA_DIR` | `<repo>/data` | Parquet + CSV files (relative paths resolve from the repo root). |
| `STATE_DB` | `backend/state.db` | SQLite file for goals, chat feedback and linked accounts. |
| `VERDA_INFERENCE_KEY`, `LLM_*` | none | Used by the agent (see `app/agent/README.md`). The key is a `SecretStr` and is never logged or returned. |
| `CORS_ORIGINS` | empty | Extra browser origins, comma-separated or a JSON list. Production is same-origin and needs none. `*` allows everything (not recommended). |
| `CORS_ORIGIN_REGEX` | localhost + private LAN | Development origins on any port (`localhost`, `127.0.0.1`, `*.localhost`, `10.x`, `192.168.x`, `172.16–31.x`). Empty string switches it off. |
| `CHAT_RATE_PER_IP_PER_MIN` | `60` | `POST /api/chat` requests per client address per minute (`0` = off). |
| `CHAT_RATE_PER_CUSTOMER_PER_MIN` | `120` | The same per `customer_id` (the demo customers are shared). |
| `FEEDBACK_RATE_PER_IP_PER_MIN` | `60` | `POST /api/chat/feedback` per client address per minute. |
| `CHAT_MAX_CONCURRENT_LLM` | `8` | Chat turns that may use the LLM at the same time. Others wait `CHAT_QUEUE_WAIT_S` (`1.0`) and are then answered by the offline coach. |
| `CHAT_MAX_MESSAGE_CHARS` | `4000` | Longest user message. |
| `CHAT_MAX_HISTORY_MESSAGES` | `60` | Most messages accepted in one request. |
| `CHAT_HISTORY_CHAR_BUDGET` | `12000` | Characters of older conversation passed to the model (newest kept). |
| `CHAT_MAX_IMAGE_BYTES` | `4000000` | Largest decoded photo. |
| `MAX_BODY_BYTES` | `8000000` | Largest request body on any route. |
| `MAX_GOALS_PER_CUSTOMER` | `20` | Goals one customer can hold. |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | How long a write waits for another worker's lock. |

## Limits and errors (public demo)

All limits are in-process, so with `uvicorn --workers 2` each worker counts on its own (the
effective ceiling is up to twice the configured number). Every message below is returned in
en, fi or sv.

| Case | Response |
|---|---|
| Too many chat or feedback requests | `429` JSON `{"detail": …}` with a `Retry-After` header |
| Body larger than `MAX_BODY_BYTES` (with or without `Content-Length`) | `413` JSON `{"detail": …}` |
| Message too long, too many messages, photo too large or not an image | `200` SSE stream with a single `error` event; the LLM is not called |
| All LLM slots busy | normal SSE answer from the offline coach (same tools and widgets) |
| Goal amount not finite, negative or above 10 000 000 €, blank name, more than `MAX_GOALS_PER_CUSTOMER` goals | `422` JSON `{"detail": …}` |
| Query values out of range (dates, sizes, huge numbers) | `422` |
| Unexpected server error | `500` JSON `{"detail": …}`; the traceback goes to the server log only |

The client address is the socket peer. `X-Forwarded-For` is read only when the peer is
`127.0.0.1` / `::1` (the local reverse proxy); a header sent from anywhere else is ignored.
Goal names are stored without control characters and angle brackets and are passed to the
model as quoted data.

`GET /api/health` answers at once, also while the DuckDB cache is being built on first boot.
`status` is `ok`, `starting` (cache loading or building) or `degraded` (the load failed and
is retried); `ready` is the same as a boolean, `data.state` is `ready | loading | error`,
`llm.primary` / `llm.fallback` say what is configured and `llm.available` whether this worker
can reach a model right now. `GET /api/ready` returns `200` once the data is loaded and `503`
before that. Data routes called during the first build wait for it.

`state.db` runs in WAL mode with the busy timeout above. Schema creation and demo seeding run
in one transaction and retry while another worker holds the lock, so two workers can start on
an empty file at the same time. Goals are read from SQLite on every request; nothing about
goals is cached per worker.

## Layout

```
app/config.py        typed settings (pydantic-settings)
app/limits.py        rate limits, LLM concurrency cap, body / message / photo limits
app/db.py            DuckDB: materialised cache, per-customer slices, parameterised helpers
app/store.py         SQLite: goals (seeded for demo customers), feedback, linked accounts
app/demo.py          the six demo customers (fictional display labels)
app/content.py       lessons/personas JSON, localisation, data-driven lesson unlocks
app/i18n.py          request locale (en / fi / sv) for analytics texts and labels
app/analytics/       one module per SPEC §3.1 function (pure, JSON-serialisable results)
app/routers/         thin REST layer: customers.py, meta.py (+ chat.py from the agent)
tests/               pytest: data layer, every analytics function, REST smoke tests, i18n
```

## Languages (en / fi / sv)

Every route accepts `?locale=en|fi|sv` (anything else, e.g. `de` or `sv-FI`, is normalised
and never an error; unknown → English). The locale only changes human texts: basket
names and "why" texts, rules, nudges and their `action_prompt`, safe-to-spend explanation,
survival tips, goal-plan summary and cut tips, home-readiness gaps, archetype names and
trait details, merchant/MCC/category labels (`Matbutik #22`), month and weekday labels,
seeded demo goal names, demo taglines, benchmark source notes and 404 messages. Keys,
enums, numbers and ISO dates never change, so clients can switch language without
re-mapping anything. Money in fi/sv prose uses `1 234,50 €` and dates `30.9.2026`.

How: `app/i18n.py` keeps the current locale in a `ContextVar`, set by a small ASGI
middleware from the query string (and by the agent from the chat turn language);
analytics code calls `tr(en, fi, sv)`, and the memoisation cache keys on the locale.
Translations live next to the English text they mirror; data-file texts (`mcc.json`,
`lessons.json`, `personas.json`) carry `{en, fi, sv}`.

## Performance and safety

* **Materialise once.** `tx` = Parquet rows ≤ AS_OF, sorted by customer, enriched with a
  stable `id`, the recurring flag, the outlier flag and the `basket` column. Peer statistics
  (`peer_category`, `peer_flows`) and behaviour traits (`customer_traits`) for all
  5 100 customers are precomputed in the same build.
* **Per-customer slices.** The first request for a customer copies their ~700 rows into an
  in-memory schema. Any SQL written as `... FROM tx WHERE customer_id = ? ...` runs on that
  slice automatically. Pure ledger analytics are memoised (`analytics/cache.py`). A home
  screen overview takes about 70 ms warm and 200–400 ms cold on a laptop.
* **No raw SQL from the LLM.** The MyData engine (`query.py`) only takes typed filters.
  Every value is a bound parameter, `group_by` comes from a whitelist, and the customer id
  is always the first predicate, so one customer can never see another's rows.

---

## Analytics methods

### 1. The three baskets (`analytics/baskets.py`)

One SQL `CASE` (`classify_sql()`) is the single source of truth. It runs once at build time,
so every screen, the agent and the tests read the same `basket` column. `classify(row)` is
a Python mirror, and a test checks it against the SQL on 20 000 sampled rows. Rules are
applied in order and the first match wins:

| # | Basket | Rule | Why |
|---|---|---|---|
| 1 | income | Salary, Other Income, Invest Withdraw (or any positive amount) | money in |
| 2 | saving | Invest Deposit, Salary Sweep | money set aside |
| 3 | fixed | Housing, Utilities | must-pay monthly bills |
| 4 | irregular | Health (all) | necessary but lumpy |
| 5 | irregular | Home & Tech at MCC 5200/5251 (hardware, home supply) or any Home & Tech > 150 € | repairs, big needs |
| 6 | irregular | Fuel, service station or parking (5541/5542/7523) > 80 € | car costs arrive in chunks |
| 7 | irregular | One-off essential outlier: Groceries/Transport/Utilities > max(3 × the customer's median ticket, 120 €) | unusual spike |
| 8 | fixed | Recurring merchant: ≥ 4 payments in ≥ 4 months, median gap 25–35 days, amount CV < 0.25 | behaves like a subscription |
| 9 | fixed | Groceries at MCC 5411/5422/5451 or with no MCC | everyday food |
| 10 | fixed | Public transport (4111) | commuting |
| 11 | leak | Everything else: restaurants/cafés/bars, kiosks (5499), taxis (4121), entertainment, lifestyle, travel, gadgets under the threshold | flexible spending |

`get_baskets` returns monthly totals (the running month is flagged `partial`), the current
month's top contributors per basket, and plain-language `explanations`.
Invariant (tested): `fixed + irregular + leak` equals the total spending reported by `query_spending`.

### 2. Safe-to-spend (`analytics/safe_to_spend.py`)

```
safe_total     = balance − upcoming bills before payday − irregular buffer − goal contributions
safe_per_day   = safe_total / days_until_payday
safe_this_week = safe_per_day × min(7, days_until_payday)
```

* **Next payday**: median day-of-month of Salary credits over about 7 months (falls back to
  any income). If this month's salary already arrived, payday is next month. If the usual
  day has passed without a salary, the salary counts as late and we plan until the end of
  the month (the conservative choice).
* **Upcoming bills**: recurring streams (see 3) projected forward. In the running month only
  the unpaid remainder counts. A saving transfer that normally follows the salary is
  skipped while this month's salary has not arrived.
* **Irregular buffer**: average monthly irregular basket (6 complete months) × days / 30.44.
* **Goal contributions**: Σ `monthly_contribution` of active goals × days / 30.44.
* **Status**: `safe_per_day` compared with the customer's typical daily flexible spend
  (leaks plus non-bill fixed spending, last 3 months): `comfortable` ≥ 90 %, `tight` ≥ 40 %,
  otherwise `critical`.

### 3. Recurring payments (`analytics/recurring.py`)

Bill categories without a merchant id (Housing, Utilities, Invest Deposit, Salary Sweep)
count as monthly when they appear in ≥ 4 of the last 6 months. Utilities come as several
payments a month, so the amount is the monthly total. A merchant stream counts as monthly
when its median gap is 25–35 days and its amount CV is < 0.25. It counts as weekly when the
gap is 6–8 days and there are ≥ 8 payments.

### 4. Spender profile (`analytics/profile.py`)

Eight traits are measured over 6 complete months. Each score is a **percentile among all
5 100 customers**, so 82 means "more than 82 % of customers":
savings power (1 − spend/income), leak share, weekend share (Fri–Sun) of leaks, small treats
(leaks < 15 € per week), big splurges (leaks > 100 € per month), late night (purchases
22:00–05:00), steadiness (inverse month-to-month CV) and cushion (lowest balance ÷ monthly spend).

| Archetype | Match score |
|---|---|
| Tightrope Walker 🎪 | 100 if the balance closed below zero on ≥ 3 days, else 0.7 × (100 − cushion) |
| Squirrel Saver 🐿️ | 0.5 savings power + 0.5 cushion |
| Impulse Splurger ⚡ | 0.5 big splurges + 0.25 (100 − steadiness) + 0.25 late night |
| Latte Leaker ☕ | 0.6 small treats + 0.2 leak share + 0.2 (100 − savings power) |
| Weekend Treater 🎉 | 0.7 weekend + 0.3 leak share |
| Steady Planner 🧭 | mean(steadiness, cushion, 100 − leak share) |

The highest score wins. All scores and trait details are returned so the UI can explain the label.

### 5. Benchmarks (`analytics/benchmarks.py`)

* **Peers**: same age band in the dataset (18–29, 30–39 … 70+). For each category: peer
  median, p25, p75, and your percentile (ties count half; peers with no spend count as 0).
* **Statistics Finland** (`app/data/benchmarks_fi.json`, parsed defensively): Household
  Budget Survey 2022 euros per consumption unit by age group, median disposable income by
  age, household saving rate. `stat_fi_monthly` is `null` when a figure is unavailable.

### 6. What-if (`analytics/whatif.py`)

Baseline = average monthly spend of the matching transactions over 6 complete months. Each
spending group is matched by the **first** adjustment that fits, so overlapping
adjustments never double count. `with_return` compounds the monthly saving at the given
annual rate (monthly compounding). It teaches the time value of money and is not investment advice.

### 7. Goals and the goal planner (`analytics/goals.py`, `store.py`)

`surplus` = income − spending (6-month average; money moved to savings counts as surplus)
− other goals' monthly contributions. `needed = remaining / months`, `gap = max(0, needed −
surplus)`. Suggested cuts come from the leak basket, biggest euro saving first, using realistic
cut rates: eating out 30 %, taxis 50 %, entertainment 25 %, lifestyle 30 %, kiosk 40 %,
travel 20 %, gadgets 25 %. Feasibility is `on_track` (no gap), `stretch` (the cuts cover the
gap) or `unrealistic` (a `suggested_deadline` is given when a later date would work). When the
surplus is negative no date works: `suggested_deadline` is `null`, the summary says that more
goes out than comes in, and the coach does not offer the "create goal" step. Amounts must be
finite and between 0 and 10 000 000 €. The original five demo customers start with two goals;
Joni starts with one goal to close his initial 784.58 € account deficit.

### 8. Survival plan (`analytics/survival.py`)

Bills due before `until` (default: next payday) are listed, and automated savings are
paused. With no amount given, the plan starts from the balance minus bills. With an explicit
amount ("…with 300 €") it treats that amount as money to live on. Flexible-category budgets
start from typical daily spend: essentials (groceries, transport, health) first at a lean
85 %, then the rest shared across leak categories. Risk is `ok`, `tight` or `short`, and
`shortfall` gives the missing amount.

### 9. Home readiness (`analytics/mortgage.py`)

Learned from the 200-application mortgage dataset at runtime: required monthly income ≈
1.84 % of the loan (linear fit, R² ≈ 1), median approved LTV ≈ 85 % (so equity ≈ 15 %), and
closing costs ≈ 2.6 % (median transfer tax). The customer's side: 6-month average income,
plus an equity estimate of balance + net amount moved to savings in the last 12 months.
The result adds an annuity estimate (25 years at 4 %), a 6 % stress test, the verdict
`ready` / `almost` / `not_yet` with concrete gaps, and, if the customer applied before, their
real application with its timeline and a lesson for the rejection reason.

### 10. Nudges (`analytics/nudges.py`) and recovery (`analytics/recovery.py`)

Rule-based, deterministic and persona-neutral, returning 3–6 items: low safe-to-spend, leak
pace ±20 % against the usual month, the goal closest to completion, the biggest cuttable leak
(with its yearly saving), the next bill, a savings-rate celebration, and the spender
archetype. Each nudge carries an `action_prompt` that opens the chat with that question.

Recovery-first support overrides that list when the situation is not ordinary. A negative
balance is `balance_repair`; a non-negative balance with a negative six-full-month average
surplus is `cashflow_stabilizing`; both non-negative is `ordinary`; missing or non-finite data
is `unknown`, never a fake green. Recovery nudges are one primary plus at most two supporting
messages (essential bills, then the ongoing deficit, then a small buffer when affordable) and
avoid peer comparison, archetype, investing and savings-streak pressure. Safe-to-spend urgency
stays separate from insolvency; `goal_reservations_present` reports included reservations, not a proven cause of tightness.
The overview payload and the agent grounding add the same `recovery` field additively, so the
chat fallback answers with the same numbers. See `tests/test_recovery.py` and
`tests/test_recovery_chat.py`. No-tool answer checks allow displayed figures, sums/differences
and arithmetic using user-supplied operands, but not arbitrary scaling of context numbers
(e.g. monthly surplus × 30 must not validate an invented rent). Unit conversions based only
on account context require a data tool; the offline grounding evaluator is unchanged.

Recovery regression coverage: `tests/test_recovery.py` and `tests/test_recovery_chat.py`
(require the challenge dataset).
