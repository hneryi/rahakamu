#!/usr/bin/env bash
# SPankkiBot quality gate: backend tests, offline agent evals, mobile typecheck, API smoke test.
# Exits non-zero if any step that could run failed. Steps whose part isn't built yet are SKIPPED
# (with a clear message) unless STRICT=1, in which case a skip counts as a failure.
#
# Usage: scripts/check.sh [--no-smoke] [--ui]
#   --no-smoke   skip the API smoke test
#   --ui         also run the Playwright UI tests (needs the web app on :8081, see e2e/README.md)
# Env:  API_BASE (http://localhost:8000)  STRICT (0)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${API_BASE:-http://localhost:8000}"
STRICT="${STRICT:-0}"
RUN_SMOKE=1
RUN_UI=0
for arg in "$@"; do
  case "$arg" in
    --no-smoke) RUN_SMOKE=0 ;;
    --ui) RUN_UI=1 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ -t 1 ]]; then G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; B=$'\033[1m'; Z=$'\033[0m'; else G=""; R=""; Y=""; B=""; Z=""; fi

declare -a NAMES=() RESULTS=() TIMES=()
record() { NAMES+=("$1"); RESULTS+=("$2"); TIMES+=("$3"); }

# step <name> <dir> <cmd...>
step() {
  local name="$1" dir="$2"; shift 2
  echo
  echo "${B}━━ $name ━━${Z}  ($dir: $*)"
  local t0=$SECONDS
  set +e
  (cd "$dir" && "$@")
  local code=$?
  set -e
  local dt=$((SECONDS - t0))
  if ((code == 0)); then record "$name" PASS "${dt}s"; echo "${G}✔ $name passed${Z}"
  else record "$name" FAIL "${dt}s"; echo "${R}✘ $name failed (exit $code)${Z}"; fi
}
skip() { echo; echo "${Y}↷ SKIP $1 — $2${Z}"; record "$1" SKIP "-"; }

api_up() {
  if command -v curl >/dev/null; then curl -fsS -m 3 "$API_BASE/api/health" >/dev/null 2>&1
  else python3 - "$API_BASE" <<'PY' >/dev/null 2>&1
import sys, urllib.request; urllib.request.urlopen(sys.argv[1] + "/api/health", timeout=3)
PY
  fi
}

# 1. backend pytest
if [[ ! -f "$ROOT/backend/pyproject.toml" ]]; then skip "backend pytest" "backend/pyproject.toml missing"
elif ! command -v uv >/dev/null; then skip "backend pytest" "uv not installed"
elif ! find "$ROOT/backend/tests" -name 'test_*.py' 2>/dev/null | grep -q .; then
  skip "backend pytest" "no backend/tests/test_*.py yet"
else step "backend pytest" "$ROOT/backend" uv run pytest -q
fi

# 2. agent evals (offline, deterministic)
if [[ -f "$ROOT/backend/app/agent/evals/run.py" || -f "$ROOT/backend/app/agent/evals/run/__main__.py" ]]; then
  if command -v uv >/dev/null; then step "agent evals (offline)" "$ROOT/backend" uv run python -m app.agent.evals.run --offline
  else skip "agent evals (offline)" "uv not installed"; fi
else skip "agent evals (offline)" "backend/app/agent/evals/run.py not built yet"
fi

# 3. mobile typecheck
if [[ ! -f "$ROOT/mobile/tsconfig.json" ]]; then skip "mobile typecheck" "mobile/tsconfig.json missing"
elif [[ ! -d "$ROOT/mobile/node_modules" ]]; then skip "mobile typecheck" "run 'cd mobile && npm install' first"
else step "mobile typecheck" "$ROOT/mobile" npx tsc --noEmit
fi

# 4. API smoke test (needs a running backend)
if ((RUN_SMOKE)); then
  if ! command -v uv >/dev/null; then skip "API smoke" "uv not installed"
  elif ! api_up; then skip "API smoke" "backend not reachable at $API_BASE (start it with scripts/dev.sh --backend-only)"
  else step "API smoke" "$ROOT" uv run --quiet --with httpx python e2e/api_smoke.py --base "$API_BASE"
  fi
fi

# 5. optional Playwright UI tests
if ((RUN_UI)); then
  if [[ ! -d "$ROOT/e2e/node_modules/@playwright/test" ]]; then skip "UI e2e (Playwright)" "run 'cd e2e && npm install && npx playwright install chromium'"
  else step "UI e2e (Playwright)" "$ROOT/e2e" npx playwright test
  fi
fi

# summary
echo
echo "${B}┌────────────────────────────┬────────┬────────┐${Z}"
printf "${B}│ %-26s │ %-6s │ %-6s │${Z}\n" "check" "result" "time"
echo "${B}├────────────────────────────┼────────┼────────┤${Z}"
fail=0
for i in "${!NAMES[@]}"; do
  r="${RESULTS[$i]}"; c="$G"
  [[ "$r" == FAIL ]] && { c="$R"; fail=1; }
  [[ "$r" == SKIP ]] && { c="$Y"; ((STRICT)) && fail=1; }
  printf "│ %-26s │ ${c}%-6s${Z} │ %6s │\n" "${NAMES[$i]}" "$r" "${TIMES[$i]}"
done
echo "${B}└────────────────────────────┴────────┴────────┘${Z}"
if ((fail)); then echo "${R}${B}CHECK FAILED${Z}"; exit 1; fi
echo "${G}${B}ALL CHECKS PASSED${Z} (skipped steps are not failures; STRICT=1 to enforce)"
