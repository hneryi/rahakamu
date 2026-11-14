# Rahakamu — Product & Engineering Spec (source of truth for all builders)

Rahakamu is a **Personal Economic Trainer** for S-Bank (S-Pankki) customers, built for the Junction 2026 S-Pankki challenge.

Rahakamu is the display name. Technical identifiers remain unchanged: `spankkibot` slug/scheme, `fi.junction.spankkibot` bundle/package, package names, persistence keys, logs, deployment identifiers and `SPankkiBotHost`.
Customers *talk with their own money* through one of two animated AI characters. The app is mobile-native
(Expo / React Native, iOS + Android) and also runs as a web app that can be embedded in S-mobiili via WebView.

## 0. Judging criteria → what we must nail (20 % each)
| Criterion | How Rahakamu wins it |
|---|---|
| Impact on financial literacy (pedagogy) | The **three baskets** model (fixed essentials / irregular essentials / everyday leaks) is everywhere: home meter, chat answers, lessons. Every AI answer may end with a short "💡 Concept" tip. Learn tab = "Money Gym" micro-lessons + quizzes, unlocked by the user's own data. |
| Originality of AI integration | Tool-calling agent over the user's real data; **generative UI** (tools emit typed widgets the app renders inline: charts, what-if sliders, goal plans); two personas with distinct pedagogy; voice in/out; vision (snap a price tag / receipt → "can I afford this?"); proactive nudges; transparent "Based on N transactions" sources. |
| Clarity of mobile UX | One home screen: money status on top, character docked at bottom, ask anything by typing or holding to talk. Sleek dark-green S-Bank inspired theme, haptics, smooth Reanimated motion. |
| Feasibility | Runs on the provided synthetic dataset (3.6 M tx, 5 100 customers) with DuckDB; open-weights Nemotron model via OpenAI-compatible API (self-hostable, EU-friendly); offline rule-based fallback; tests. |
| Potential to integrate into S-mobiili | Clean REST + SSE API, stateless agent, widget protocol, Expo app that ships as native modules or embeddable web build; i18n en/fi; docs/S-MOBIILI_INTEGRATION.md. |

## 1. Data
Files in `data/` (repo root): `transactions.parquet` (converted from `tx_junction_transactions.csv`, `tx_timestamp` already parsed to TIMESTAMP),
`tx_customers_junction.csv` (customer_id, customer_postal_code (keep as VARCHAR, leading zeros!), customer_age),
`mtg_tx_customer_link_and_final_mtg_infio.csv` (mortgage outcomes, 200 rows), `mtg_negotiation_history.csv` (mortgage events).
CSVs have a UTF-8 BOM. Transactions columns: customer_id, bank_account_id (1 account per customer), tx_date DATE, tx_timestamp TIMESTAMP,
category, tx_amount_eur (negative = money out), balance_after_eur, transaction_type, merchant_id (nullable, e.g. MRC-GRO-0035), mcc_code (nullable BIGINT).
Range 2024-10-01 … 2026-09-30. ~700 tx per customer.

Categories: Groceries, Restaurants, Transportation, Utilities, Entertainment, Health, Salary, Home & Tech, Housing, Lifestyle, Travel,
Invest Deposit, Other Income, Salary Sweep, Invest Withdraw.
transaction_type: purchase, utilities_payment, salary, housing_payment, investment_deposit, other_income, salary_sweep, investment_withdrawal.
MCC codes present: 5411 5499 5422 5451 (groceries); 5812 5814 5813 (restaurants/fast food/bars); 5542 5541 7523 4111 4121 (fuel, fuel, parking, transit, taxi);
7922 7999 7832 7991 7996 (entertainment); 5912 8011 8099 8021 (pharmacy, doctor, health, dentist); 5200 5732 5251 5712 5734 (home & tech);
5941 5651 5999 5691 5942 5945 (lifestyle); 4722 4511 7011 7512 (travel). Many rows have null MCC.

**"Today" = AS_OF date**, env `AS_OF_DATE`, default `2026-09-18` (mid-month so "this month" is in progress). Every analytic ignores tx after AS_OF.
Current balance = `balance_after_eur` of last tx ≤ AS_OF.

### 1.1 Demo customers (persona picker in the app)
| id | label | why |
|---|---|---|
| CUST05020 | "Emma, 21" student-ish, small income, leaky | young adult literacy story |
| CUST00584 | "Leo, 22" dips below zero | survive-the-month story |
| CUST00586 | "Mika, 39" high income, big leaks | invest / goal story |
| CUST00961 | "Sanna, 41" mortgage rejected | home-readiness story |
| CUST00001 | "Pirjo, 63" steady saver | benchmark story |
| CUST05014 | "Joni, 23" negative balance, repair→payday loan story | back-to-positive story |
Display names and the repair/payday-loan backstory are fictional demo labels, not facts inferred from the ledger. Any other customer_id also works via the API.
Joni was selected by the lowest latest transaction balance as of 2026-09-18: -784.58 €
(`arg_max(balance_after_eur, (tx_timestamp, id))` per customer in the existing read-only cache).
His age (23) and postal code (00487) come from the synthetic dataset.

## 2. The three baskets (core pedagogy) — `basket` field
- `fixed` — **Mandatory & regular**: Housing, Utilities, Groceries with MCC 5411/5422/5451 or null-MCC groceries, Transportation 4111 (public transit), detected recurring payments (same merchant or category, roughly monthly cadence, amount CV < 0.25).
- `irregular` — **Mandatory & irregular**: Health (all), Home & Tech with MCC 5200/5251 (hardware/repair) or any Home & Tech tx > 150 €, Transportation 5541/5542/7523 (fuel/parking/car) when amount > 80 €, Travel 4511 when it is family/annual (keep simple: Travel → leak unless flagged), one-off large outliers in essential categories.
- `leak` — **Everyday spending that slips through your fingers**: Restaurants (5812/5814/5813), Entertainment, Lifestyle, Groceries 5499 (convenience/kiosk), Transportation 4121 (taxi), Travel, Home & Tech 5732/5734/5712 under the irregular threshold, everything else discretionary.
- Non-spending flows: `income` (Salary, Other Income, Invest Withdraw), `saving` (Invest Deposit, Salary Sweep).
Classification lives in ONE function `app.analytics.baskets.classify(row)` / SQL CASE, plus `app/data/mcc.json` labels. Must be explainable: each basket has `why` text.

## 3. Backend (Python 3.13, FastAPI, DuckDB, uv) — `backend/`
```
backend/
  pyproject.toml            # uv project; deps pinned there
  app/main.py               # FastAPI app, CORS *, mounts routers under /api
  app/config.py             # settings from env / ../.env (AS_OF_DATE, DATA_DIR, LLM_* , VERDA_INFERENCE_KEY)
  app/db.py                 # DuckDB connection (thread-safe cursor per call), views tx / customers / mortgages, as_of filtering
  app/analytics/            # pure functions, each returns pydantic models or plain dicts (JSON-serialisable)
  app/store.py              # SQLite (backend/state.db) for goals + chat feedback + linked accounts; seeded goals for demo customers
  app/routers/              # thin REST layer
  app/agent/                # LLM agent (see §4)
  app/data/                 # mcc.json, benchmarks_fi.json, lessons.json, personas.json
  tests/
```
Run: `cd backend && uv run uvicorn app.main:app --reload --port 8000`. Never log or return the API key.

### 3.1 Analytics function contract (agent tools call these; keep names & signatures EXACT)
All take `customer_id: str` first; dates are ISO strings or `date`; money rounded to 2 decimals; return JSON-serialisable dicts.
```python
# app/analytics/overview.py
def get_overview(customer_id) -> dict  # see GET /overview response
def get_balance(customer_id) -> dict   # {"balance": float, "as_of": str, "trend_30d": [{"date","balance"}]}
# app/analytics/query.py   (the MyData engine — flexible, safe, parameterised; NO raw SQL from the LLM)
def query_spending(customer_id, start=None, end=None, category=None, basket=None, merchant=None, mcc=None,
                   group_by="none", direction="out", top_n=20) -> dict
   # group_by in {"none","category","basket","month","week","weekday","merchant","hour","day"}
   # returns {"filters": {...}, "total": float, "count": int, "avg_tx": float,
   #          "groups": [{"key": str, "label": str, "total": float, "count": int}], "period": {"start","end"}}
def search_transactions(customer_id, start=None, end=None, category=None, basket=None, merchant=None,
                        min_amount=None, max_amount=None, text=None, limit=50, offset=0) -> dict
   # {"items": [Tx], "total_count": int}
# app/analytics/baskets.py
def classify_sql() -> str              # SQL CASE expression producing basket
def get_baskets(customer_id, months=6) -> dict
   # {"months":[{"month":"2026-09","fixed":..,"irregular":..,"leak":..,"income":..,"saving":..}],
   #  "current_month": {...same + "top": {"fixed":[{"label","total"}],"irregular":[...],"leak":[...]}},
   #  "explanations": {"fixed": str, "irregular": str, "leak": str}}
# app/analytics/safe_to_spend.py
def safe_to_spend(customer_id) -> dict
   # {"balance","next_payday","days_until_payday","upcoming_bills":[{"label","amount","expected_date"}],
   #  "irregular_buffer","goal_contributions","safe_total","safe_per_day","safe_this_week","status":"comfortable|tight|critical","explanation": str}
# app/analytics/recurring.py
def recurring_payments(customer_id) -> dict  # {"items":[{"label","category","merchant_id","avg_amount","cadence":"monthly|weekly|...","day_of_month","last_date","basket"}],"monthly_total"}
# app/analytics/profile.py
def spender_profile(customer_id) -> dict
   # {"archetype": {"key","name","emoji","description"}, "traits":[{"key","label","score":0-100,"detail"}],
   #  "savings_rate", "leak_share", "weekend_share", "small_tx_per_week", "late_night_share", "volatility"}
   # archetypes: steady_planner, weekend_treater, latte_leaker, impulse_splurger, squirrel_saver, tightrope_walker (often near/below zero)
# app/analytics/benchmarks.py
def benchmarks(customer_id) -> dict
   # {"peer_group": {"label":"Age 18-25 in dataset","size":int},
   #  "categories":[{"category","you_monthly","peer_median_monthly","peer_p25","peer_p75","percentile","stat_fi_monthly": float|None}],
   #  "income": {...same}, "savings_rate": {...}, "sources":[{"name","url","note"}]}
# app/analytics/whatif.py
def simulate_what_if(customer_id, adjustments: list[dict], horizon_months=12, invest_return_pct=0.0) -> dict
   # adjustments: [{"category": "Restaurants"} or {"basket":"leak"} or {"merchant": id}, "change_pct": -20}]
   # {"baseline_monthly","new_monthly","monthly_saving","horizon_months","total_saving","with_return","per_item":[...],"series":[{"month":1,"cumulative":..}]}
# app/analytics/goals.py
def list_goals(customer_id) -> list[dict]
def create_goal(customer_id, name, target_amount, deadline=None, emoji=None, kind="other", saved_amount=0.0) -> dict
def update_goal(customer_id, goal_id, **fields) -> dict
def delete_goal(customer_id, goal_id) -> dict
def plan_goal(customer_id, target_amount, deadline=None, name=None, saved_amount=0.0) -> dict
   # {"name","target_amount","saved_amount","deadline","months","needed_per_month","current_monthly_surplus",
   #  "gap","feasibility":"on_track|stretch|unrealistic","suggested_deadline",
   #  "cuts":[{"label","category","basket","current_monthly","cut_pct","monthly_saving","why"}], "cuts_total", "summary"}
   # cuts come mostly from the leak basket, realistic cut % per category (restaurants 30, taxi 50, entertainment 25, lifestyle 30, convenience 40, travel 20), biggest first, until gap covered.
# app/analytics/survival.py
def survival_plan(customer_id, amount=None, until=None) -> dict
   # amount default = current balance, until default = next payday
   # {"amount","until","days","upcoming_bills_total","bills":[...],"free_money","per_day","per_week",
   #  "category_budgets":[{"category","budget","typical"}],"risk":"ok|tight|short","shortfall","tips":[str]}
# app/analytics/mortgage.py
def home_readiness(customer_id, property_price=None) -> dict
   # Uses mortgage dataset ratios (required_monthly_income vs loan, typical LTV, approval vs rejection reasons) + customer's income/savings.
   # {"property_price","loan_needed","equity_needed","your_equity_estimate","required_monthly_income","your_monthly_income","ltv","verdict":"ready|almost|not_yet","gaps":[str],"dataset_note", "customer_application": {...}|None}
# app/analytics/nudges.py
def nudges(customer_id) -> list[dict]  # [{"id","kind":"celebrate|warn|tip|goal","text","emoji","action_prompt"}]  rule-based, 3-6 items
# app/analytics/recovery.py
def classify(balance, monthly_surplus) -> str  # pure: balance_repair | cashflow_stabilizing | ordinary | unknown
def recovery(customer_id, sts=None) -> dict
   # {"state","months":6,"balance","monthly_income","monthly_spending","monthly_surplus","deficit",
   #  "goal_monthly_need","planned_monthly_change","urgency","safe_per_day","days_until_payday",
   #  "goal_contributions","goal_reservations_present","tx_count","period"}
```

**Recovery-first support.** A negative balance always wins (`balance_repair`); otherwise a
negative six-full-month average surplus means `cashflow_stabilizing`; both non-negative is
`ordinary`; missing or non-finite inputs are `unknown` (never a fake green). Recovery nudges
are one primary plus at most two supporting messages: everyday essential bills first, then the
ongoing deficit correction, then a small buffer once affordable. They skip peer comparison,
archetype, investing encouragement and savings-streak pressure. Safe-to-spend urgency
(`critical|tight|comfortable`) stays separate from debt/insolvency, and goal reservations that
make it tight are reported as such rather than blamed on food. Goal progress never changes the
balance, and a transient payday balance does not declare a permanent recovery. The overview
payload adds the same `recovery` field additively; the agent grounding and fallback read it
from the shared computation. Tests: `backend/tests/test_recovery.py` (classification boundaries,
demo customers, payday snapshots, goal invariance, nudge/action routing in en/fi/sv) and
`mobile/tests/fixtures.test.cjs` (mirrored classification, nudge and stream routing).
`Tx` shape: `{"id": str, "date": "2026-09-17", "timestamp": iso, "amount": -12.5, "category", "basket", "merchant_id", "merchant_label", "mcc", "mcc_label", "icon": emoji, "balance_after", "type"}`.
`merchant_label`: friendly generic label derived from MCC + merchant number, e.g. "Café #12", "Grocery store #35", "Taxi #3". NEVER use real brand names.

### 3.2 REST API (all under `/api`, JSON, CORS open)
| Method | Path | Returns |
|---|---|---|
| GET | /health | {"status":"ok","as_of","llm":{"primary":bool}} |
| GET | /customers/demo | [{"customer_id","name","age","postal_code","tagline","avatar_emoji"}] |
| GET | /customers/{id}/overview | {"customer":{id,name,age,postal_code},"as_of","balance","trend_30d":[...],"month":{"income","spent","saved","by_basket":{"fixed","irregular","leak"}},"safe_to_spend":{safe_to_spend()},"recovery":{recovery()},"goals":[Goal],"recent_transactions":[Tx x8],"nudges":[...]} |
| GET | /customers/{id}/transactions?start&end&category&basket&merchant&text&limit&offset | search_transactions |
| GET | /customers/{id}/spending?start&end&category&basket&group_by | query_spending |
| GET | /customers/{id}/baskets?months=6 | get_baskets |
| GET | /customers/{id}/safe-to-spend | safe_to_spend |
| GET | /customers/{id}/recurring | recurring_payments |
| GET | /customers/{id}/profile | spender_profile |
| GET | /customers/{id}/benchmarks | benchmarks |
| POST | /customers/{id}/what-if | body {adjustments,horizon_months,invest_return_pct} → simulate_what_if |
| GET/POST | /customers/{id}/goals | list / create (body = create_goal kwargs) |
| PATCH/DELETE | /customers/{id}/goals/{goal_id} | update / delete |
| POST | /customers/{id}/goals/plan | body {target_amount,deadline,name,saved_amount} → plan_goal |
| GET | /customers/{id}/survival?amount&until | survival_plan |
| GET | /customers/{id}/home-readiness?property_price | home_readiness |
| GET | /customers/{id}/nudges | nudges |
| GET | /lessons?locale=en | lessons.json (localised) |
| GET | /personas | personas.json |
| POST | /chat | **SSE stream**, see §4.2 |
| POST | /chat/feedback | {message_id, rating: 1|-1, comment?} |
Goal: `{"id","name","emoji","kind":"car|travel|home|emergency|education|gadget|other","target_amount","saved_amount","deadline":str|null,"monthly_contribution","progress":0..1,"created_at"}`.
Seed goals: the first five demo customers get 2 (e.g. "Emergency fund 🛟", plus one fitting: car/travel/home/laptop) with partial progress. Joni gets one goal, "Back in the black 🎯" (784.58 €, nothing saved, deadline 2027-09-18), which tracks a plan to close his initial account deficit. Recorded goal progress does not change the ledger balance, and the target is not the full payday-loan balance or a loan repayment. A one-time top-up migration adds Joni's goal to stores seeded before he existed.

## 4. AI agent — `backend/app/agent/`
- `llm.py`: OpenAI-compatible client (official `openai` python SDK, AsyncOpenAI) with provider chain from env:
  primary `LLM_PRIMARY_BASE_URL` + `LLM_PRIMARY_MODEL` (Nemotron 3.5 Super VL — vision + tools, returns `reasoning` field; never show reasoning text to users, but surface a "thinking" status), fallback `LLM_FALLBACK_*`, key `VERDA_INFERENCE_KEY`. Timeouts, 1 retry, then offline fallback.
- `personas.py` + `app/data/personas.json`: two characters sharing all tools but with distinct voice & pedagogy:
  - **Sisu** 🐻 — "The Trainer". Energetic Finnish bear coach, tough-love, fitness metaphors (money muscles, reps, streaks, PRs), short punchy sentences, celebrates wins, challenges the user ("7-day no-takeaway challenge?"). Colour: amber `#F5A524`.
  - **Aava** 🦉 — "The Mentor". Calm, warm owl teacher, explains *why* in plain language, uses analogies, asks one reflective question, Socratic. Colour: teal/mint `#3DD9B4`.
- `tools.py`: OpenAI tool schemas + executors wrapping §3.1 functions: get_overview, query_spending, search_transactions, get_baskets, safe_to_spend, recurring_payments, spender_profile, benchmarks, simulate_what_if, list_goals, plan_goal, create_goal, update_goal, survival_plan, home_readiness, explain_concept(topic) (from lessons.json), render_chart(title, chart_type, data) (lets the model visualise any query result).
  Each executor returns `ToolResult(llm_payload: dict (compact, aggregated), widgets: list[Widget], sources: dict(tx_count, period))`. The LLM only sees aggregates (privacy by design), never other customers' data.
  Writes (create_goal/update_goal) are proposed first: the agent emits an `action_buttons` widget ("Create goal 'Car' 12 000 € by 2027-06") and the app calls the REST endpoint on confirm — OR the tool is called when the user explicitly confirms.
- `orchestrator.py`: tool loop (max 6 rounds), streaming final answer tokens; system prompt = persona + rules + user context summary (name, age, as_of date, balance, payday, basket shares, goals) + locale. Rules: answer with numbers from tools only (never invent figures); keep mobile-short (≤120 words unless asked); always relate spending to the 3 baskets when relevant; end with optional one-line "💡" concept; investing = general education only, not personalised investment advice, mention risk & that S-Bank advisors can help; respond in user's language (fi/en/sv).
- `fallback.py`: offline intent router (keywords en+fi: balance/saldo, spend/kulutin, save for/säästää, safe to spend/turvallisesti, survive/selviän, what if/entä jos, what kind of spender/millainen kuluttaja, goal/tavoite, subscriptions/tilaukset, home/asunto) → calls the same tools → templated persona answer + widgets. Used when LLM is down. Must make the demo fully work offline.
- Vision: if request has `image_base64`, send as `image_url` data URI to Nemotron VL; prompt it to read price/receipt and then reason with safe_to_spend / goals.
- `evals/`: 15+ scripted questions from the challenge brief ("How much did I spend on taxis last month?", "What kind of spender am I?", "What is safe for me to spend this week?", "How much could I save if I reduced dining out by 20%?", "Help me save for a car that costs 12000", "How do I survive this month with 300 €?") with expected tool calls; a runner `uv run python -m app.agent.evals.run` printing pass/fail.

### 4.2 Chat SSE protocol — `POST /api/chat`
Request: `{"customer_id","persona":"sisu|aava","locale":"en|fi","messages":[{"role":"user|assistant","content":str}],"image_base64": str|null}`
Response: `text/event-stream`, each event `event: <type>\ndata: <json>\n\n`:
- `status` `{"state":"thinking|tool|writing","label":"Checking your restaurant spending…"}`
- `tool` `{"name","args","summary"}` (after each tool finishes)
- `widget` `{"id","type", "data"}` (see §5.3)
- `token` `{"text"}` (streamed answer text, markdown-lite: **bold**, lists)
- `done` `{"message_id","sources":{"tx_count":int,"period":str,"tools":[str]},"suggestions":[str x3],"mood":"happy|neutral|concerned|celebrate"}`
- `error` `{"message"}`
`mood` drives the character's animation.

## 5. Mobile app — `mobile/` (Expo SDK 58, expo-router, TypeScript strict, React 19, Reanimated 4, react-native-svg)
Check the [Expo SDK 58 documentation](https://docs.expo.dev/versions/v58.0.0/) before using an API. Use `npx expo install` when adding Expo dependencies.
Installed: react-native-svg, expo-speech (TTS), expo-speech-recognition (STT; needs dev build — must gracefully degrade on Expo Go/web without it; on web use Web Speech API if available), expo-haptics, expo-linear-gradient, expo-blur, @react-native-async-storage/async-storage, expo-image-picker, expo-localization, zustand, @tanstack/react-query.
SSE on native: use `import { fetch } from 'expo/fetch'` (supports streaming response bodies); parse SSE manually.
API base URL: `process.env.EXPO_PUBLIC_API_URL` (default `http://localhost:8000`). `EXPO_PUBLIC_MOCK=1` → use local fixtures (`src/api/fixtures.ts`) so the UI runs without backend.

### 5.1 Structure
```
mobile/src/
  app/_layout.tsx            # providers (QueryClient, theme, i18n), Stack
  app/(tabs)/_layout.tsx     # custom floating glass tab bar: Home, Insights, Goals, Learn
  app/(tabs)/index.tsx       # HOME
  app/(tabs)/insights.tsx    # MyData explorer: basket trends, spender profile, benchmarks, free filters
  app/(tabs)/goals.tsx       # goals list + create
  app/(tabs)/learn.tsx       # Money Gym lessons/quizzes, streak
  app/chat.tsx               # full-screen chat (modal/sheet presentation)
  app/onboarding.tsx         # pick demo customer + pick character (Sisu or Aava)
  app/settings.tsx           # language, voice on/off, character, customer switch, data/privacy explainer
  api/ (client.ts, types.ts, sse.ts, fixtures.ts, hooks.ts)
  characters/                # OWNED BY CHARACTER BUILDER: index.ts exports <Character persona state size/>
  components/                # BalanceCard, SafeToSpendCard, GoalCarousel, BasketMeter, TxRow, CharacterDock, ChatBubble, Composer(mic, camera, send), widgets/*
  components/widgets/        # WidgetRenderer + one component per widget type
  i18n/ (en.ts, fi.ts, index.ts)
  store/ (session.ts: customerId, persona, locale, voice; chat.ts)
  theme/ (tokens.ts)
```
### 5.2 Home screen (the hero)
Top → bottom: greeting row ("Hei Emma 👋", date, settings) · **BalanceCard** (balance, 30-day sparkline, month income/spent) · **SafeToSpendCard** ("Safe to spend today 23 €", week amount, payday countdown, status colour) · **GoalCarousel** (horizontal cards with progress ring, emoji, € left, months) · **BasketMeter** (this month split fixed/irregular/leak, tap = explanation) · **Recent transactions** (8 rows, icon, label, basket dot, amount).
Bottom (absolute, above tab bar): **CharacterDock** — the chosen character (≈110 px, idle animation) with a speech bubble cycling `nudges`; below it a pill composer "Ask Sisu anything…" + mic (press-and-hold to talk) + camera. Tapping composer or bubble opens `/chat` with the text/nudge prefilled. Character reacts (listening while mic held).
### 5.3 Chat & generative-UI widgets
Chat screen: character large at top (state from SSE: thinking → talking while tokens stream → mood at done), messages list, status line ("Checking your restaurant spending…"), suggestions chips from `done.suggestions`, sources chip ("Based on 42 transactions · Sep 2026", expandable to show tools used), 👍/👎 feedback, TTS read-aloud toggle (expo-speech, persona pitch/rate: Sisu pitch 0.9 rate 1.05; Aava pitch 1.1 rate 0.95).
Widget types (`type` → `data`):
- `kpi` {items:[{label,value:number,unit:"€"|"%"|"",delta?:number,tone?:"good|bad|neutral"}]}
- `bar_chart` {title, unit, bars:[{label,value,highlight?:bool}]}
- `line_chart` {title, unit, points:[{x:string,y:number}], target?:number}
- `donut_chart` {title, unit, slices:[{label,value,color?}]}
- `basket_breakdown` {month, fixed, irregular, leak, explanations:{fixed,irregular,leak}, top:{fixed:[..],irregular:[..],leak:[..]}}
- `safe_to_spend` (safe_to_spend() payload)
- `goal_plan` (plan_goal() payload) + "Create this goal" button
- `what_if` {base_adjustments, result: simulate_what_if(), slider:{category|basket, min:-100, max:0, value}} — interactive: slider re-calls POST /what-if live
- `transaction_list` {title, items:[Tx], total}
- `spender_profile` (spender_profile() payload)
- `benchmark` (benchmarks() payload subset)
- `survival_plan` (survival_plan() payload)
- `home_readiness` (home_readiness() payload)
- `lesson` {id,title,body,emoji,quiz?:{question,options:[..],answer_index}}
- `action_buttons` {buttons:[{label, kind:"prompt|create_goal|open_tab", payload}]}
Unknown widget types render nothing (forward compatible).
### 5.4 Design language
Dark-first, premium. Background `#07140F` → `#0B1F17` gradient, surfaces `rgba(255,255,255,0.06)` glass with 1 px `rgba(255,255,255,0.08)` border, radius 24, primary S-green `#00B26F` (accent mint `#3DD9B4`), Sisu amber `#F5A524`, warn `#FF6B5A`, text `#F2F7F4` / muted `#9FB3A9`. Basket colours: fixed `#5B8DEF`, irregular `#F5A524`, leak `#FF6B8A`. Typography: system font, big tabular numbers for money (fontVariant tabular-nums), sizes 34/22/17/15/13. Generous spacing (16/24), subtle shadows, haptics on primary actions, spring animations. Also provide a light theme via tokens. Must look great at 390×844 and work on web (max-width 480 centred column on desktop).
### 5.5 i18n
All UI strings in `i18n/en.ts` and `i18n/fi.ts`; locale default from expo-localization, switchable in settings; sent to /chat.

## 6. Characters — `mobile/src/characters/` (react-native-svg + Reanimated, no image assets needed)
`export function Character(props: {persona: "sisu"|"aava"; state: "idle"|"listening"|"thinking"|"talking"|"happy"|"concerned"|"celebrate"; size?: number})`
Original vector designs (no copyrighted characters). Sisu: friendly round bear, amber/brown, small sweatband (trainer), whistle. Aava: soft teal owl, big round glasses, tiny book. Animations: idle breathing + blinking; listening (ear/feather perk, pulsing ring); thinking (eyes look up, 3 dots); talking (mouth open/close loop); happy (bounce); concerned (brows tilt); celebrate (jump + confetti sparkles). Also export `PERSONAS` meta {name, title, color, emoji, voice:{pitch,rate}}.

## 7. Docs (repo root `docs/`) — written at the end, must match the code
README.md (pitch, screenshots, quickstart), docs/ARCHITECTURE.md (mermaid), docs/API.md, docs/AI_AGENT.md, docs/DATA_AND_METHODS.md (baskets, safe-to-spend, profile, benchmarks + sources), docs/JUDGING_CRITERIA.md, docs/S-MOBIILI_INTEGRATION.md, docs/DEMO_SCRIPT.md, docs/ROADMAP.md.

## 6b. UPDATE (user request): human cartoon characters replace the bear/owl
The two personas keep their names, roles, colours and voices, but are **friendly, intellectual human cartoon characters** (half-body, expressive, modern flat-with-soft-shading illustration style, original designs):
- **Sisu — "The Trainer"**: Finnish man, late 20s, warm grin, tousled sandy-brown hair, short neat beard, thin modern glasses, amber quarter-zip sweater with a small S-green detail, smartwatch, often holds a stopwatch or tablet; energetic gestures (thumbs-up, fist pump, pointing at chart).
- **Aava — "The Mentor"**: Finnish woman, mid 30s, kind smile, dark-brown hair in a loose bun with a pencil, round tortoiseshell glasses, teal cardigan over a cream blouse, holds a notebook; calm gestures (pushes glasses, open palm explaining, finger raised for an idea).
Same component API as §6. Built in `mobile/src/characters-human/` first, then swapped into `mobile/src/characters/`. Persona prompts must describe them as humans (no bear/owl references).

## 5.6 UPDATE (user request): trilingual voice chat — Finnish, English, Swedish
- Locales: `en`, `fi`, `sv` everywhere (UI i18n adds `i18n/sv.ts`; /chat `locale` accepts `sv`; personas.json, lessons and fallback intents get Swedish too).
- Speech-to-text: expo-speech-recognition with `lang` = `fi-FI` | `en-US` | `sv-SE` (web: Web Speech API same tags). A language pill (FI / EN / SV) sits next to the mic; default = app locale. The recognised text is sent with that locale.
- Text-to-speech: expo-speech with `language` = `fi-FI` | `en-US` | `sv-SE`, choose the best available voice for that language via `Speech.getAvailableVoicesAsync()` (fallback to default), persona pitch/rate on top. Auto-read replies aloud when the user asked by voice (hands-free loop).
- Agent: replies in the language of the user's message (detect), else the selected locale; status labels & suggestions localised for all three.
