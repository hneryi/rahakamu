# Rahakamu — mobile app

Expo SDK 58 · React Native 0.88 · React 19 · expo-router · Reanimated 4 · react-native-svg · TanStack Query · zustand.
Runs on **iOS, Android and web** from one codebase. The web build is a static SPA that can be embedded in the
S-mobiili WebView as-is.

> Customers *talk with their own money* through an animated coach (Sisu the trainer or Aava the mentor).
> Every answer is grounded in the customer's real transactions, comes with charts they can play with, and teaches
> the **three baskets** model: fixed essentials, irregular essentials and everyday leaks.

## Quick start

Use **Node.js 22 LTS (22.13 or newer) or 24 LTS (24.3 or newer)** (Expo SDK 58).

```bash
cd mobile
npm ci                      # install the locked dependencies
npm run web:mock            # web, offline demo data (no backend needed)
npm run web                 # web against the backend at http://<host>:8000
npx expo start              # scan the QR with a dev build / Expo Go
```

| Env var | Default | Meaning |
|---|---|---|
| `EXPO_PUBLIC_API_URL` | auto | Backend base URL. Auto-detected otherwise: web = same host `:8000`; device = Metro host's LAN IP `:8000`; Android emulator = `10.0.2.2:8000`. |
| `EXPO_PUBLIC_MOCK` | unset | `1` serves everything from `src/api/fixtures.ts`. |

**Offline-safe by design:** if the backend is unreachable (network error, timeout, 5xx) every request — including the
streaming chat — falls back to the on-device demo engine and a small amber **"Demo data"** badge appears. The client
re-probes the backend after 20 s, so the app heals itself when the server comes back.

Voice input needs a development build on native (`npx expo run:ios|android` or `eas build --profile development`);
in Expo Go the mic shows a toast and focuses the keyboard. See **Languages & voice** below.

## Checks

```bash
node tests/branding.test.cjs # Rahakamu display names + stable technical identifiers
npm run typecheck           # tsc --noEmit (strict)
npm run lint                # expo lint (eslint-config-expo + React Compiler rules)
npm run build:web           # static export to dist/
npx expo-doctor             # 20/20 checks
```

## Display name

The app is **Rahakamu**. Existing `spankkibot` technical identifiers and persisted storage
keys stay unchanged. Native display names and permission texts require a new native build.
Legacy outlined marketing wordmarks are documented in [the brand kit](../design/BRAND.md).

## Structure

```
src/
  app/                      # expo-router routes (every file is a screen)
    _layout.tsx             # providers: gestures → safe area → React Query → nav theme; Stack; desktop phone frame
    (tabs)/_layout.tsx      # headless tabs + floating glass tab bar; onboarding gate
    (tabs)/index.tsx        # HOME: balance, safe-to-spend, goals, three-basket meter, recent tx, character dock
    (tabs)/insights.tsx     # MyData explorer: basket trend, categories + drill-down, profile, benchmarks, recurring
    (tabs)/goals.tsx        # goals with progress rings; create/edit sheet with live plan preview
    (tabs)/learn.tsx        # Money Gym: data-recommended lessons, quiz, streak
    chat.tsx                # full-screen chat: character reacts to the SSE stream; generative-UI widgets
    onboarding.tsx          # pick demo customer → pick coach
    settings.tsx            # language, voice, theme, coach, customer, privacy explainer, backend status
  api/
    types.ts                # TypeScript mirror of the REST/SSE/widget contract (docs/SPEC.md)
    client.ts               # typed endpoint map, base-URL resolution, fixture fallback
    sse.ts                  # POST /api/chat streaming (expo/fetch on native) + incremental SSE parser
    hooks.ts                # TanStack Query hooks (keys include customer id + locale)
    fixtures.ts             # deterministic offline demo engine (generated tx history + analytics + chat stream)
  characters/               # Sisu & Aava (owned by the character module)
  components/
    widgets/                # WidgetRenderer + one component per widget type
    charts/                 # hand-built SVG charts: bar, line+target, donut, stacked baskets, ring, sparkline
    home/ chat/ ui/         # cards, dock, composer, mic, bubbles, primitives (Sheet, Slider, Segmented…)
  i18n/                     # en.ts (keys) + fi.ts + sv.ts (typed: a missing key is a compile error), formatters
  store/                    # zustand: session (persisted), chat (persisted per customer), learn, ui
  theme/                    # design tokens (dark + light) and makeStyles()
  hooks/                    # useVoiceInput (STT), useSpeech (TTS), debounce
  lib/speechLang.ts         # language tags, reply-language detection, best-voice ranking
```

## Generative UI (widget protocol)

The agent's tools emit typed widgets over SSE (`event: widget`, `{id, type, data}`); `WidgetRenderer` maps `type` to a
component. Unknown types render nothing (forward-compatible) and every widget sits in its own error boundary, so a
malformed payload removes one card, never the conversation.

| type | component | interaction |
|---|---|---|
| `kpi` | `KpiWidget` | animated numbers, good/bad tone |
| `bar_chart` / `line_chart` / `donut_chart` | chart widgets | animated entrance; line supports a target line |
| `basket_breakdown` | `BasketBreakdownWidget` | tap a basket → why it exists + top items |
| `safe_to_spend` | `SafeToSpendWidget` | shows the full formula (balance − bills − buffer − goals) |
| `goal_plan` | `GoalPlanWidget` | **Create this goal** → `POST /goals`, caches invalidated, haptic, character celebrates |
| `what_if` | `WhatIfWidget` | gesture-handler + Reanimated slider; debounced live `POST /what-if` |
| `transaction_list` | `TransactionListWidget` | evidence behind an answer |
| `spender_profile` / `benchmark` | profile / benchmark views | reused on Insights |
| `survival_plan` / `home_readiness` | plan widgets | budgets vs typical, gaps |
| `lesson` | `LessonWidget` | inline quiz; counts towards the Money Gym streak |
| `action_buttons` | `ActionButtonsWidget` | `prompt` / `create_goal` (user-confirmed writes) / `open_tab` |

## Chat ↔ character

`status: thinking|tool` → character *thinking* · `token` stream or TTS → *talking* · `done.mood` → *happy / concerned /
celebrate* for a few seconds → *idle*. Holding the mic → *listening*. The sources chip ("Based on 42 transactions ·
Sep 2026") expands to the tools used; 👍/👎 posts to `/api/chat/feedback`. TTS uses the persona's pitch and rate
(`PERSONAS[id].voice`).

## Languages & voice (SPEC §5.6)

**UI languages: Suomi, English, Svenska.** The device language picks the default (`sv-*` → Svenska, `fi` → Suomi,
anything else → English); Settings and the onboarding header switch it. Strings live in `src/i18n/{en,fi,sv}.ts`;
`fi.ts` and `sv.ts` are typed `Record<TKey, string>`, so a missing key fails `npm run typecheck`. Swedish uses
Finland-Swedish banking words (lön, hyra, saldo, sparmål, räkningar). Money and dates follow the locale:
fi and sv `1 234,56 €` and `17.9.2026` (non-breaking spaces, so amounts never wrap), en `€1,234.56` and `17 Sep 2026`.
The locale goes to the API as `?locale=` and in the chat body; the offline fixtures (lessons, nudges, basket
explanations, starter chips, the scripted chat) exist in all three languages.

**Talking to the coach.** Tap the mic to start and tap again to send (the recogniser also stops by itself after a
pause), or hold it and let go to send. Interim words appear live in the composer (on Home, in the coach's bubble) and
the character switches to *listening*. The **FI / EN / SV pill** next to the mic sets the *spoken* language
(`fi-FI`, `en-US`, `sv-SE`). It defaults to the UI language, one tap cycles, and the choice is remembered until the
UI language changes. A question spoken in another language is sent with that language as `locale`, so the coach
answers in it.

**Read-aloud.** If you asked by voice, the answer is read aloud automatically; typed questions are not. A
**Stop reading** pill shows while it speaks, pressing the mic stops playback, and Settings → *Spoken answers* (or the
speaker button in the chat header) turns it off. The reply's language is detected from its text (falling back to the
spoken language), then the best installed voice for it is picked: exact tag first (`fi-FI`; `en-US`, then `en-GB`;
`sv-SE`, then `sv-FI`), then enhanced / natural / neural voices, then on-device ones, with robotic engines last.

| Platform | Speech-to-text | Text-to-speech | Notes |
|---|---|---|---|
| Chrome / Edge (desktop, Android) | ✅ Web Speech API (`webkitSpeechRecognition`), cloud recogniser | ✅ `speechSynthesis` (Edge ships "Natural" online voices) | Chrome's recogniser needs network |
| Safari (macOS, iOS) | ✅ `webkitSpeechRecognition` (Siri dictation must be on) | ✅ system voices | |
| Firefox | ❌ no recogniser: toast, keyboard gets focus | ✅ `speechSynthesis` | |
| S-mobiili WebView | depends on the host WebView (untested; Android System WebView usually has none) | ✅ | falls back to typing |
| iOS / Android dev build | ✅ `expo-speech-recognition` (on-device where the OS supports it) | ✅ `expo-speech`, enhanced voices when installed | mic permission prompt on first use |
| Expo Go | ❌ native module missing: toast + keyboard | ✅ `expo-speech` | |
| Mic permission denied | ❌ toast + keyboard | ✅ | |

Voices are whatever the device has installed: if no Finnish or Swedish voice exists, the OS default voice reads the
text with the right language tag. Tested here in headless Chromium with stubbed `SpeechRecognition` and
`speechSynthesis` (all three languages); the other rows are from platform documentation, not yet tried on devices.

## Design system

All visual decisions live in `src/theme/tokens.ts` (SPEC §5.4): background `#07140F → #0B1F17`, glass surfaces
`rgba(255,255,255,0.06)` + 1 px hairline, radius 24, S-green `#00B26F`, mint `#3DD9B4`, Sisu amber `#F5A524`,
basket colours fixed `#5B8DEF` / irregular `#F5A524` / leak `#FF6B8A`, type scale 34/22/17/15/13, tabular numerals
for money, shared spring presets. A complete light palette uses the same semantic names (Settings → Appearance), so
re-skinning for S-mobiili is a one-file change. On desktop web the app renders in a 480 px phone frame; layouts are
verified at 360 px width with no horizontal overflow.

## Integrating into S-mobiili

- **WebView:** `npm run build:web` → host `dist/` and open it in a WebView. Deep links work as routes:
  `/chat?q=What%20is%20safe%20to%20spend%3F&send=1`, `/goals?new=1`, `/insights`.
- **Native:** the screens are plain React Native; the customer id would come from the host session instead of
  onboarding (`useSession().setCustomer`), and `API_BASE` from host config.
- **Privacy:** the client only renders what the backend returns; the agent only ever sees aggregates of the
  signed-in customer's own data.
