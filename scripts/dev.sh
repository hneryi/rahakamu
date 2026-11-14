#!/usr/bin/env bash
# SPankkiBot dev runner: starts the FastAPI backend (:8000) and the Expo web app (:8081)
# together, prefixes their logs, and shuts both down cleanly on Ctrl-C.
#
# Usage: scripts/dev.sh [--backend-only|--mobile-only] [--mock]
#   --mock         run the mobile app against local fixtures (EXPO_PUBLIC_MOCK=1), no backend needed
# Env:  BACKEND_PORT (8000)  MOBILE_PORT (8081)  EXPO_PUBLIC_API_URL (http://localhost:$BACKEND_PORT)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-8000}"
MOBILE_PORT="${MOBILE_PORT:-8081}"
RUN_BACKEND=1
RUN_MOBILE=1
MOCK=0

for arg in "$@"; do
  case "$arg" in
    --backend-only) RUN_MOBILE=0 ;;
    --mobile-only)  RUN_BACKEND=0 ;;
    --mock)         MOCK=1; RUN_BACKEND=0 ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [[ -t 1 ]]; then
  C_B=$'\033[38;5;79m'; C_M=$'\033[38;5;214m'; C_G=$'\033[38;5;35m'; C_R=$'\033[31m'; C_0=$'\033[0m'
else
  C_B=""; C_M=""; C_G=""; C_R=""; C_0=""
fi

PIDS=()
cleanup() {
  local code=$?
  trap - INT TERM EXIT
  if ((${#PIDS[@]})); then
    echo
    echo "${C_G}[dev]${C_0} shutting down…"
    for pid in "${PIDS[@]}"; do
      # kill the whole process group of each child (uvicorn reloader / expo + metro workers)
      kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    done
    for _ in $(seq 1 50); do
      local alive=0
      for pid in "${PIDS[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1; done
      ((alive)) || break
      sleep 0.1
    done
    for pid in "${PIDS[@]}"; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  fi
  exit "$code"
}
trap cleanup INT TERM EXIT

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

# start <name> <color> <dir> <cmd...>  — runs in its own process group with prefixed output
start() {
  local name="$1" color="$2" dir="$3"; shift 3
  set -m
  (cd "$dir" && exec "$@" 2>&1 | sed -u "s/^/${color}[${name}]${C_0} /") &
  PIDS+=("$!")
  set +m
}

if ((RUN_BACKEND)); then
  if [[ ! -f "$ROOT/backend/pyproject.toml" || ! -f "$ROOT/backend/app/main.py" ]]; then
    echo "${C_R}[dev]${C_0} backend/app/main.py not found — backend not built yet, skipping backend." >&2
    RUN_BACKEND=0
  elif ! command -v uv >/dev/null; then
    echo "${C_R}[dev]${C_0} 'uv' not installed (https://docs.astral.sh/uv/) — skipping backend." >&2
    RUN_BACKEND=0
  elif port_busy "$BACKEND_PORT"; then
    echo "${C_R}[dev]${C_0} port $BACKEND_PORT already in use — assuming backend is already running." >&2
    RUN_BACKEND=0
  else
    start backend "$C_B" "$ROOT/backend" uv run uvicorn app.main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
  fi
fi

if ((RUN_MOBILE)); then
  if [[ ! -f "$ROOT/mobile/package.json" ]]; then
    echo "${C_R}[dev]${C_0} mobile/package.json not found — skipping mobile." >&2
    RUN_MOBILE=0
  else
    if [[ ! -d "$ROOT/mobile/node_modules" ]]; then
      echo "${C_G}[dev]${C_0} installing mobile dependencies (npm install)…"
      (cd "$ROOT/mobile" && npm install)
    fi
    node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
    if ((node_major < 22)); then
      echo "${C_R}[dev]${C_0} warning: Node $(node -v 2>/dev/null || echo '?') detected; Expo SDK 58 requires Node >= 22.13 (nvm install 22)." >&2
    fi
    export EXPO_PUBLIC_API_URL="${EXPO_PUBLIC_API_URL:-http://localhost:$BACKEND_PORT}"
    if ((MOCK)); then export EXPO_PUBLIC_MOCK=1; fi
    export CI="${CI:-}"   # keep Expo interactive unless caller set CI
    start mobile "$C_M" "$ROOT/mobile" npx expo start --web --port "$MOBILE_PORT"
  fi
fi

if ((${#PIDS[@]} == 0)); then
  echo "${C_R}[dev]${C_0} nothing to start." >&2
  exit 1
fi

echo
echo "${C_G}┌──────────────────────── SPankkiBot dev ────────────────────────┐${C_0}"
((RUN_BACKEND)) && echo "${C_G}│${C_0}  API      http://localhost:$BACKEND_PORT/api/health"
((RUN_BACKEND)) && echo "${C_G}│${C_0}  API docs http://localhost:$BACKEND_PORT/docs"
((RUN_MOBILE))  && echo "${C_G}│${C_0}  Web app  http://localhost:$MOBILE_PORT   (mock=$MOCK, api=${EXPO_PUBLIC_API_URL:-n/a})"
((RUN_MOBILE))  && echo "${C_G}│${C_0}  Phone    scan the Expo QR code below with Expo Go"
echo "${C_G}│${C_0}  Ctrl-C to stop everything"
echo "${C_G}└────────────────────────────────────────────────────────────────┘${C_0}"
echo

# exit when any child exits (then cleanup kills the rest)
set +e
wait -n "${PIDS[@]}"
code=$?
set -e
echo "${C_R}[dev]${C_0} a process exited (code $code); stopping the others."
exit "$code"
