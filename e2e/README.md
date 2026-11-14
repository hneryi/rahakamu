# Rahakamu e2e

| What | Command |
|---|---|
| Everything (pytest, offline evals, tsc, API smoke) | `scripts/check.sh` (`--ui` adds Playwright, `STRICT=1` makes skips fail) |
| API smoke: every SPEC §3.2 route ×2 customers + 3 SSE chats | `uv run --with httpx python e2e/api_smoke.py [--base http://localhost:8000] [--customers CUST05020,CUST00584] [--skip-chat] [--json out.json]` |
| UI flows at 390×844 (screenshots → `e2e/screenshots/`) | `cd e2e && npm install && npx playwright install chromium && npx playwright test` |
| UI flows without backend (app fixtures) | `cd e2e && E2E_MOCK=1 npx playwright test` |
| SPEC-shaped stub API (canned data, for self-tests only) | `uv run --with fastapi --with uvicorn python e2e/mock_backend.py --port 8000` |

Playwright reuses a web app already running on `:8081` (e.g. from `scripts/dev.sh`), otherwise starts
`npx expo start --web --port 8081` in `mobile/`. `E2E_BASE_URL=…` targets any deployed web build.

Specs: `01` onboarding → Emma → Sisu → home (balance, safe-to-spend, goals, basket meter, 8 transactions, dock) ·
`02` "How much did I spend on restaurants last month?" → streamed answer + widget + suggestions/sources ·
`03` switch to Aava in settings; fi-FI locale (UI + Finnish chat) · `04` Insights / Goals / Learn tabs.

The tests locate elements by `testID` (react-native-web → `data-testid`) with accessibility-label fallbacks.
The full testID contract is in `tests/helpers.ts` (`TID`).
