# Rahakamu — Pitch Narrative

8 slides, about 3 minutes with the live demo embedded at slide 4. The HTML deck lives in `pitch/slides.html` (arrow keys to move, `F` for fullscreen, `N` for notes).

---

## Slide 1 — Problem: "Money disappears, and nobody explains why"

**On slide**
- Banking apps show *what* you spent. Almost none teach *why* it's gone.
- Young adults get most of their money advice from social media, not their bank.
- Budget apps nag. Spreadsheets get abandoned in week two.
- Headline: **"I don't know where my money goes."**

**Speaker notes**
> Every bank app has a transaction list. That's a receipt drawer, not a coach. People don't fail at money because they can't add up. They fail because the small, everyday spending is invisible until the month is gone. Emma, 21, our persona, loses about a thousand euros a month to things she wouldn't call "spending". S-Bank asked for a personal economic trainer. Here it is.

---

## Slide 2 — Insight: three baskets

**On slide**
- 🟦 **Fixed:** mandatory and regular (rent, utilities, groceries, transit, subscriptions)
- 🟧 **Irregular:** mandatory but surprising (dentist, car repair, a new fridge)
- 🟥 **Leaks:** everyday spending that slips through your fingers (takeaway, taxis, impulse buys)
- "You can't cut rent this month. You *can* plug a leak today."

**Speaker notes**
> The single most useful money idea we found is splitting spending into three baskets. Fixed you plan, irregular you buffer for, leaks you train. Every screen, every AI answer and every lesson in Rahakamu uses this one mental model. Repeated in context, it turns into literacy. The classification is deterministic and explainable: category, MCC code, amount and recurrence, each with a "why".

---

## Slide 3 — Solution: a personal trainer for your money

**On slide**
- **One home screen:** safe to spend today, three-basket meter, goals, recent transactions
- **Talk with your own money:** type, hold to talk, or snap a photo
- **Two coaches:** Sisu 🐻 the Trainer (tough love, challenges, streaks) and Aava 🦉 the Mentor (calm, explains *why*)
- **Money Gym:** micro-lessons and quizzes unlocked by *your* data
- Placeholders: home and chat screenshots

**Speaker notes**
> Rahakamu is a mobile-native app. Open it and you see one number you can trust: what's safe to spend today, after bills and goals. Below that are the three baskets. At the bottom, your coach. Sisu, the energetic bear, will challenge you to a 7-day no-takeaway streak. Aava, the owl, will explain compound interest with an analogy and ask you one good question. Same data, same tools, two ways to learn.

---

## Slide 4 — Live demo (Emma, 21)

**On slide**
- "What kind of spender am I?" → spender profile
- "Help me save for a car, it costs 12 000 €" → goal plan, leaks to plug, create goal
- "What if I cut dining out by 20 %?" → live slider
- Aava: "Miten selviän tästä kuusta 300 eurolla?" → survival plan
- Money Gym lesson unlocked, then 📸 "Can I afford this?"

**Speaker notes**
> Switch to the phone. Follow `pitch/DEMO_SCRIPT.md` exactly. If the network dies, say: "We designed for this. The offline engine uses the same tools, so the numbers are identical." If the demo cannot run at all, use the screenshots on this slide.

---

## Slide 5 — AI architecture: grounded, generative, open

**On slide**
- **Nemotron 3.5 Super VL**: open-weights, tools and vision, OpenAI-compatible, EU self-hostable
- **17 tools** over a DuckDB MyData engine (3.6 M tx): query_spending, baskets, safe_to_spend, plan_goal, what-if, survival_plan, benchmarks…
- **Generative UI**: tools emit typed widgets (charts, sliders, goal plans, lessons) that the app renders inline
- **Grounded by design**: numbers only from tools, aggregates only to the model, sources chip on every answer
- **Resilient**: provider chain, then an offline rule-based fallback over the same tools
- Diagram: App → SSE `/api/chat` → Orchestrator (persona + rules) ⇄ Tools → DuckDB; widgets → App

**Speaker notes**
> The LLM never does maths and never sees raw rows. It decides *which* analysis to run. Deterministic Python and SQL computes the answer, and the model explains it in persona. Tools also return widgets, so the answer arrives as an interactive what-if slider or a goal plan with a create button, not a wall of text. Writes are confirm-first. And because it's open-weights behind an OpenAI-compatible interface, S-Bank can host it in its own EU data centre and swap models later.

---

## Slide 6 — Impact on financial literacy

**On slide**
- **Learn in context:** every answer can end with a 💡 concept; insights unlock Money Gym lessons
- **One mental model everywhere:** three baskets on home, in chat, in lessons
- **Behaviour, not just knowledge:** safe-to-spend, goals, challenges, streaks, proactive nudges
- **Two pedagogies:** coaching (Sisu) and Socratic mentoring (Aava)
- **Measurable:** quiz mastery, leak share over time, goal progress, days under safe-to-spend

**Speaker notes**
> Literacy isn't a course you finish. It's a habit you build where the money actually moves. We teach one concept at the moment it's relevant, using your own numbers. That's far stickier than a generic article. Benchmarks come from peers in the dataset and Statistics Finland, always cited. And the outcomes are measurable, so S-Bank can prove impact in a pilot.

---

## Slide 7 — Integration into S-mobiili and the business case

**On slide**
- **Drop-in:** REST and SSE API, stateless agent, versioned widget JSON; embed the web build via WebView or go native
- **Built for S-Bank:** runs on S-Bank's transaction schema; fi/en (sv next); dark S-green brand
- **Cheap to run:** home screen is pure analytics with zero LLM cost; the LLM runs only on questions
- **Business value:** engagement (a daily-open reason), trust, younger customer acquisition, warm hand-offs to savings, funds and mortgage advisors
- Mortgage readiness already prototyped on the mortgage dataset

**Speaker notes**
> We built this to be adopted, not admired. S-mobiili can embed the web build in a week or consume the API natively. The agent is stateless and the widget protocol is plain JSON, so S-mobiili renders it with its own components. The cost profile is friendly because most screens need no LLM at all. Business-wise: a reason to open the bank app daily, a trusted relationship with under-25s, and natural, compliant hand-offs to S-Bank's savings and mortgage teams.

---

## Slide 8 — Team and ask

**On slide**
- **Rahakamu: a personal trainer for your money.**
- Ask: a pilot with 1 000 young S-Bank customers for 90 days; measure savings rate and leak share
- Next: real-time card nudges, shared household goals, Swedish UI, mortgage journey
- Team: [names / roles], with contact and QR placeholder
- "Kiitos! Questions?"

**Speaker notes**
> Our ask is simple: let us run a 90-day pilot with a thousand young customers and measure whether their leak basket shrinks and their savings rate grows. Everything you saw runs on S-Bank's data model with an open-weights model you can own. Kiitos!

---

## Submission description (Devpost / Junction, one paragraph)

**Rahakamu** is a mobile-native Personal Economic Trainer for S-Bank customers. You chat with your own bank data through two animated AI coaches: **Sisu 🐻**, a tough-love trainer bear, and **Aava 🦉**, a calm mentor owl. Every euro is sorted into **three baskets**: fixed essentials, irregular essentials, and everyday leaks. The home screen shows one trustworthy number, *safe to spend today*, after upcoming bills and goals. Ask anything by typing, holding to talk, or snapping a price tag ("can I afford this?"). An open-weights **Nemotron 3.5 Super VL** agent calls 17 deterministic tools over a DuckDB engine (3.6 M synthetic transactions). It answers with **generative-UI widgets** (spender profile, goal plans that cut specific leaks, live what-if sliders, survival plans) and shows the transactions each answer is based on. Insights unlock **Money Gym** micro-lessons and quizzes. Numbers never come from the LLM, the model only sees aggregates, writes are confirm-first, and an offline fallback keeps it working without the model. Built with Expo SDK 58 (iOS, Android, web) and FastAPI, in Finnish and English, and designed to drop into **S-mobiili** via REST/SSE or WebView.

## Tagline set (each ≤ 280 characters)

1. **Rahakamu: a personal trainer for your money.** Talk with your own bank data, find your leaks, and build money muscles with Sisu 🐻 and Aava 🦉. *(141 chars)*
2. Your bank app shows what you spent. Rahakamu teaches you why it's gone and what's safe to spend today. Three baskets, two AI coaches, one goal: money that stays. *(163 chars)*
3. Fixed. Irregular. Leaks. Rahakamu sorts every euro into three baskets, then an open-weights AI coach turns your own transactions into goals, what-ifs and two-minute lessons. Built for S-mobiili. *(196 chars)*
4. Snap a price tag and ask "can I afford this?" Rahakamu checks your real safe-to-spend and goals and answers honestly, in Finnish or English, with a bear or an owl. #Junction2026 #SPankki *(188 chars)*
5. Grounded, not guessed: every number in Rahakamu comes from deterministic tools over your own data. The AI explains, coaches and renders live widgets. Open-weights, EU-hostable, offline-safe. *(192 chars)*
