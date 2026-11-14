# Rahakamu — Live Demo Script

> Persona: **Emma, 21** (`CUST05020`, Helsinki 00708) — the "leaky spender".
> "Today" in the app = **2026-09-18** (`AS_OF_DATE`), mid-month, so "this month" is still in progress.
> Device: phone (390×844) mirrored to the projector, or the web build in a narrow window at 480 px.

---

## 0. Pre-flight checklist (T-15 min)

| # | Check | How |
|---|---|---|
| 1 | Backend up | `curl -s localhost:8000/api/health` → `"status":"ok"`, `"llm":{"primary":true}` |
| 2 | Emma's data loads | open the app, pick **Emma, 21**, character **Sisu** |
| 3 | Goals reset | Emma has only her 2 seeded goals (delete any "Car" goal left over from rehearsal) |
| 4 | Offline fallback works | stop the LLM (unset `LLM_PRIMARY_BASE_URL` or pull Wi-Fi on a rehearsal run) → ask "What kind of spender am I?" → still get a profile widget |
| 5 | Mic permission granted | hold the mic once; on web, allow the browser mic prompt |
| 6 | Camera/photo ready | a printed price tag (**"Wireless headphones 189 €"**) on the table, or a photo of it already in the gallery |
| 7 | Volume | TTS read-aloud on, phone volume about 60 % |
| 8 | Slides | `pitch/slides.html` open in a second tab on slide 1, fullscreen (`F`) |
| 9 | Phone | Do Not Disturb on, brightness at max, auto-lock off |

**Grounded numbers for Emma** (from the dataset, Mar–Aug 2026 averages). Use them for sanity checks only. **Say the number the app shows**, not this table.

| Fact | Approx. value |
|---|---|
| Transactions up to AS_OF | ~950 |
| Balance at 2026-09-18 | ~7 700 € |
| Housing / month | ~1 210 € (fixed) |
| Leak basket / month | ~1 060 € (Entertainment ~360, Lifestyle ~330, Restaurants ~205, Travel ~125) |
| Restaurants + fast food | ~205 €/month, so −20 % saves about 40 €/month, about 490 €/year |
| Salary day | around the 18th–20th |

Fill this in on the final rehearsal so the presenter knows what to expect:

| Screen | Value on rehearsal |
|---|---|
| Safe to spend today | ____ € |
| Archetype | ____ |
| Car plan: needed per month / feasibility | ____ € / ____ |
| What-if −20 % dining: yearly saving | ____ € |
| Survival plan 300 €: per day | ____ € |

---

## 1. The 3-minute demo (timed)

Roles: **Driver** (operates the phone) and **Narrator** (talks to the judges). One person can do both, but two is smoother.

### 0:00–0:20 · Hook (slide 1 → switch to phone)
**Say:**
> "Most banking apps tell you *what* you spent. Nobody teaches you *why* the money disappears. Meet Emma. She's 21, she has a real income, and every month about a thousand euros slips through her fingers. Let's give her a personal trainer for her money."

### 0:20–0:45 · Home glance
**Do:** show the Home screen, scroll slowly once.
**Should appear:** "Hei Emma 👋", balance card with 30-day sparkline, **Safe to spend today XX €** card (status colour plus payday countdown), goal carousel (2 seeded goals), **BasketMeter** with three colours: blue *fixed*, amber *irregular*, pink *leak*. Sisu is docked at the bottom with a nudge bubble.
**Do:** tap the **leak** segment of the BasketMeter.
**Say:**
> "One number she can trust: what's *safe to spend today*, after upcoming bills and goals. And every euro sorted into three baskets: the must-haves, the surprises, and the leaks. That three-basket model is the lesson the whole app teaches."

### 0:45–1:10 · Voice: "What kind of spender am I?" (Sisu 🐻)
**Do:** press and **hold** the mic. Sisu perks up (listening ring). Say clearly:
> **"What kind of spender am I?"**

Release. (If the mic fails, type the same sentence.)
**Should appear:** status line "Checking your spending patterns…", then Sisu's thinking animation, then a **spender_profile** widget (archetype emoji and name, trait bars: leak share, weekend share, small purchases per week), a short punchy Sisu answer, a 💡 concept line, and the chip **"Based on N transactions"**.
**Say (while it streams):**
> "That's not a canned answer. Sisu is a tool-calling agent over Emma's real transactions. It ran the profile analysis and is rendering a live widget. The model only sees aggregates, never raw rows."

### 1:10–1:40 · Goal: "Help me save for a car, it costs 12 000 €"
**Type:**
> **Help me save for a car, it costs 12 000 €**

**Should appear:** a **goal_plan** widget with target 12 000 €, needed per month, current surplus, feasibility badge (*on_track / stretch / unrealistic*) and the **cuts list, taken mostly from the leak basket** (restaurants −30 %, entertainment −25 %, lifestyle −30 %, travel −20 %), each with a "why". It ends with the button **"Create this goal"**.
**Do:** tap **Create this goal**. Light haptic. The goal appears in the carousel (show it briefly, or mention it).
**Say:**
> "It doesn't just say 'spend less'. It finds *which* leaks to plug, by how much, and whether the deadline is realistic. And writes are confirm-first: the AI proposes, Emma decides."

### 1:40–2:00 · What-if slider
**Type:**
> **What if I cut dining out by 20%?**

**Should appear:** a **what_if** widget showing monthly saving, 12-month total, cumulative line chart, and a **slider** set to −20 %.
**Do:** drag the slider to **−40 %**, then back to −20 %. The numbers update live (POST /what-if).
**Say:**
> "Generative UI: the agent hands her an interactive tool, not a paragraph. She can feel the trade-off with her thumb."

### 2:00–2:25 · Switch to Aava 🦉, Finnish
**Do:** tap the character (or Settings, then Character) and switch to **Aava**. Language follows the question.
**Type (Finnish):**
> **Miten selviän tästä kuusta 300 eurolla?**

*(Translation: "How do I get through this month on 300 euros?")*
**Should appear:** Aava answers **in Finnish**, calm and explanatory, with a **survival_plan** widget: days until payday, bills still due, free money, **per day / per week**, category budgets, risk badge, tips. She ends with one reflective question.
**Say:**
> "Same tools, different teacher. Sisu is the tough-love trainer, Aava is the calm mentor who explains *why*. Finnish, English and Swedish, chosen per message."

### 2:25–2:40 · Money Gym lesson unlocked
**Do:** tap the **lesson** widget or the suggestion chip, or jump to the **Learn** tab.
**Should appear:** a Money Gym micro-lesson (e.g. *"The three baskets"* or *"Pay yourself first"*) unlocked by her own data, plus a one-question quiz. Answer it to get a streak or celebrate animation.
**Say:**
> "Every insight turns into a two-minute lesson, unlocked by *her own* data. That's where the literacy sticks."

### 2:40–2:55 · Vision: snap a price tag
**Do:** tap the **camera** in the composer, photograph the price tag (or pick it from the gallery), and type:
> **Can I afford this?**

**Should appear:** the model reads "189 €" from the image, checks **safe to spend** and the new car goal, and gives an honest answer: "You can, but it eats N days of your safe-to-spend and pushes the car goal back X weeks." A safe_to_spend widget appears.
**Say:**
> "Nemotron VL reads the tag, then reasons with her real numbers. The question gets asked *in the shop*, before the money leaves."

### 2:55–3:00 · Close (switch to slides, S-mobiili integration slide)
**Say:**
> "Built on S-Bank's own data model, open-weights AI you can host in the EU, and a clean API and WebView build that drops into S-mobiili. Rahakamu: a personal trainer for your money. Kiitos!"

---

## 2. The 1-minute version (elevator / finalist round)

| Time | Do | Say |
|---|---|---|
| 0:00 | Home screen | "Emma, 21. Safe to spend today, three baskets: must-haves, surprises, leaks." |
| 0:12 | Hold mic: **"What kind of spender am I?"** | "A tool-calling agent over her real transactions. Live widget, sources shown." |
| 0:27 | Type **"Help me save for a car, it costs 12 000 €"**, then tap **Create this goal** | "Plugs specific leaks, checks the deadline is realistic, confirm-first." |
| 0:42 | Switch to Aava: **"Miten selviän tästä kuusta 300 eurolla?"** | "Two teachers, three languages, same grounded tools." |
| 0:55 | Close slide | "Open-weights, EU-hostable, plugs into S-mobiili. Kiitos." |

---

## 3. Failure playbook (offline mode and fallback lines)

The backend has a **rule-based offline fallback** (`app/agent/fallback.py`). It routes the same demo questions by keyword (en + fi) to the **same analytics tools** and returns templated persona answers **with the same widgets**. If the LLM is down, the demo still works and only the prose is simpler.

| Symptom | Action | Line to say |
|---|---|---|
| LLM slow (> 6 s on "thinking") | Keep talking. The orchestrator times out, retries once, then falls back automatically | "The model is thinking. While it does, notice the status line telling Emma exactly which data it's checking." |
| LLM down / venue Wi-Fi dead | Carry on: the fallback answers. If the backend itself is unreachable, restart the app with `EXPO_PUBLIC_MOCK=1` (fixtures) | "We designed for exactly this. When the model is unreachable, Rahakamu falls back to an offline engine over the same tools. The numbers are identical because they never came from the LLM in the first place." |
| Voice recognition fails or the room is noisy | Type the sentence | "Voice works, but this room is louder than a gym, so I'll type it." |
| Vision step fails (no camera on web, model error) | Skip to the close, or type **"Can I afford headphones for 189 €?"** | "Same question without the photo. The reasoning is the same: safe to spend plus goals." |
| Finnish answer comes back in English | Say it and move on | "Locale is per message. It's normally Finnish; let me show the Finnish UI instead." Then flip the language in Settings. |
| Goal already exists from rehearsal | Tap it in the carousel instead | "Emma already created it a moment ago. Here it is with its progress ring." |
| Total failure | Switch to slides 4–5 with the screenshots | "Here's the recorded run. Happy to do it live at our table afterwards." |

**Offline-safe phrasings** (these exactly match fallback keywords, so use them in a failure state):
- "What kind of spender am I?" / "Millainen kuluttaja olen?"
- "What is safe to spend this week?" / "Paljonko voin käyttää turvallisesti?"
- "Help me save for a car that costs 12000" / "Haluan säästää autoon 12000 €"
- "What if I cut restaurants by 20%?" / "Entä jos vähennän ravintoloita 20 %?"
- "How do I survive this month with 300 €?" / "Miten selviän tästä kuusta 300 eurolla?"
- "Show my subscriptions" / "Näytä tilaukset"

---

## 4. Judge Q&A prep (20 questions, crisp answers)

**1. How do you stop the AI from hallucinating numbers?**
Every figure comes from a deterministic analytics tool (DuckDB SQL over her transactions). The LLM never writes SQL and never computes money. The system prompt forbids figures that didn't come from a tool. Each answer carries a **sources chip** ("Based on 42 transactions · Sep 2026", plus the tools used). Widgets render the tool output directly, so even if the prose drifts, the chart is right. We also have an eval suite of 15+ brief questions with expected tool calls.

**2. What about privacy? Do you send transactions to an LLM?**
No raw rows by default. Tools return **compact aggregates** to the model (totals, groups, archetype scores). Transaction lists go straight to the UI as widgets and bypass the model. The model only ever sees *this* customer's data, never other customers'. And because Nemotron is open-weights, S-Bank can run it **inside its own EU infrastructure**, so data never leaves the bank.

**3. What does it cost per user?**
A typical turn is 1–3 tool calls and roughly 3–6 k tokens, mostly the system prompt and compact tool results. On a self-hosted open-weights model that is fractions of a cent per conversation. The home screen (safe to spend, baskets, nudges) is plain analytics with **zero LLM cost**. The LLM runs only when the user asks something.

**4. How does this scale to 3.5 million S-Bank customers?**
The agent is **stateless** and conversation history lives on the client. Analytics are per-customer queries that would run against S-Bank's existing transaction store (DuckDB is our hackathon stand-in). Home-screen aggregates can be precomputed nightly. LLM capacity scales horizontally with GPU replicas, and only active chatters consume it. Expect a few percent of daily actives to chat.

**5. Why open-weights (Nemotron) instead of GPT or Claude?**
Data residency and control. A bank can self-host in the EU, pin the version, audit it and fine-tune it. Nemotron 3.5 Super VL gives tool calling **and** vision in one model. Our client is OpenAI-compatible with a provider chain, so S-Bank can swap models without touching the app.

**6. Isn't this regulated financial advice?**
We stay on the **education and budgeting** side of the line. Budgeting, saving plans and spending analysis are coaching about the user's own cash flow. Investing is covered only as **general education** (risk, diversification, time horizon); the agent never recommends specific products and always points to S-Bank's licensed advisors. That rule lives in the system prompt and is covered by evals.

**7. How are the three baskets classified?**
With one explainable rule function (`classify_sql`), not the LLM. Category plus MCC plus amount plus recurrence:
- **Fixed:** housing, utilities, supermarket groceries, public transit, and detected recurring payments (roughly monthly, amount CV < 0.25).
- **Irregular:** health, home repair, large car or fuel costs, one-off big essentials.
- **Leaks:** restaurants, entertainment, lifestyle, kiosks, taxis, travel, small gadgets.

Every basket has a "why" text shown in the app, and it's deterministic and testable.

**8. Where do the benchmarks come from?**
Two sources, both labelled. (a) A **peer group in the dataset**: same age band, median and p25/p75 per category. (b) **Statistics Finland** household consumption figures where a category matches, cited with source and URL in the benchmark widget. We never present a peer number without saying where it came from.

**9. Is it accessible?**
Voice in and out (hold-to-talk, read-aloud TTS with per-persona voice), large tabular money numbers, high-contrast dark theme with a light theme option, colour plus label for baskets (never colour alone), haptics, and short ≤120-word answers by design. It is screen-reader-labelled React Native.

**10. Does it speak Swedish?**
Yes. The agent answers in the user's language (fi/en/sv are in the system prompt rules). The UI ships en and fi strings, and sv is a strings file away because all UI text is in i18n. Finland is bilingual, so for S-Bank Swedish UI is a launch requirement and cheap to add.

**11. What happens if the model is down?**
An offline rule-based router (en + fi keywords) calls the same tools and returns templated persona answers with the same widgets. The demo runs fully offline.

**12. What makes the AI integration original?**
Four things together: (1) **generative UI**, where tools emit typed widgets like interactive what-if sliders and goal plans with a create button; (2) **two personas with different pedagogy** over the same tools; (3) **vision in the moment of purchase** ("can I afford this?" from a price tag); (4) **proactive nudges** plus **lessons unlocked by your own data**.

**13. How do you measure literacy impact?**
Quiz scores and streaks in Money Gym, leak-basket share over time, goal progress, and safe-to-spend adherence (days under budget). In a pilot: A/B test nudge cohorts against a control on savings rate after 90 days.

**14. Why two characters? Isn't that gimmicky?**
People learn differently. Sisu suits users who want a push (challenges, streaks); Aava suits users who want to understand (analogies, a reflective question). Characters also lower the shame barrier: talking to a bear about your takeaway habit is easier than talking to a bank.

**15. How does it plug into S-mobiili?**
Three integration paths: (a) the REST + SSE API behind S-mobiili's existing native screens; (b) the Expo app's web build embedded in a WebView; (c) native modules. The widget protocol is versioned JSON, so S-mobiili can render widgets with its own design system. Auth would come from S-mobiili's session, and the agent is stateless.

**16. How is "safe to spend" computed?**
Balance minus bills expected before the next payday (from recurring detection), minus an irregular-expense buffer, minus planned goal contributions, divided over the days until payday. Status is comfortable, tight or critical. It's explainable: the card shows the breakdown.

**17. What about users whose income is irregular (students, gig workers)?**
Payday is detected from salary cadence. If there's none, we fall back to the month end and widen the irregular buffer. The survival plan takes an explicit amount and date ("300 € until the 20th"), so it works regardless of income pattern.

**18. Could the AI be manipulated (prompt injection) into doing something harmful?**
Its only capabilities are read-only analytics on *this* customer plus goal create/update, which is **confirm-first** via a button the app executes. It cannot move money, see other customers, or run raw SQL. Tool arguments are validated and parameterised.

**19. How accurate is the spender archetype?**
It is rule-based scoring on interpretable traits (leak share, weekend share, small purchases per week, late-night share, volatility, savings rate). The traits and their scores are shown, so the user sees *why* they're a "latte leaker". It's a conversation starter, not a credit score.

**20. What would you build next with S-Bank?**
Real-time nudges on card authorisation ("this puts your car goal back 3 days"), shared household goals, a mortgage-readiness journey linked to the loan team (already prototyped with the mortgage dataset), Swedish UI, and a pilot with 1 000 young customers measuring savings-rate change.

**Bonus one-liners**
- *Data size:* "3.6 million transactions, 5 100 customers, two years, queried live with DuckDB in milliseconds."
- *Why now:* "Under-25s get most of their money advice from social media. We put a coach inside the bank app they already open daily."
