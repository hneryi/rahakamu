"""Run the agent eval suite and print a pass/fail table.

Usage (from ``backend/``)::

    uv run python -m app.agent.evals.run            # real LLM (falls back automatically if down)
    uv run python -m app.agent.evals.run --offline  # rule-based path only
    uv run python -m app.agent.evals.run --only taxi_en,car_goal_fi --show

Checks per question
-------------------
* ``tools``     – at least one of ``expect_tools`` was called
* ``grounded``  – every number in the answer traces back to tool payloads / user context
                  (:mod:`app.agent.evals.grounding`)
* ``short``     – answer ≤ 150 words (mobile-short rule, with slack over the 120 target)
* ``clean``     – non-empty, no error event, no leaked reasoning / tool JSON
* ``done``      – a well-formed ``done`` event (3 suggestions, valid mood, sources)
* ``lang``      – the answer is written in ``expect_lang`` (default: the request locale),
                  judged by :func:`app.agent.lang.detect_language`
* ``human``     – no animal wording in the answer or status labels (Sisu and Aava are
                  human coaches)

Exit code is 1 when any question fails and ``--strict`` is given (CI-friendly).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

QUESTIONS_PATH = Path(__file__).with_name("questions.json")
MOODS = {"happy", "neutral", "concerned", "celebrate"}
ANIMAL_WORDS = re.compile(r"\b(bears?|owls?|karhu\w*|pöllö\w*|björn\w*|ugglan?|paws?|tassu\w*|feathers?|hoot\w*|growl\w*)\b|🐻|🦉", re.I)
LEAK_MARKERS = re.compile(r"<think>|</think>|\"name\"\s*:|tool_call|functions\.|query_spending|safe_to_spend\(", re.I)


def load_questions(only: set[str] | None = None) -> list[dict[str, Any]]:
    data = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    items = data["questions"]
    return [q for q in items if not only or q["id"] in only]


async def run_one(q: dict[str, Any]) -> dict[str, Any]:
    from app.agent.evals.grounding import check_grounding
    from app.agent.events import ChatRequest
    from app.agent.lang import detect_language
    from app.agent.orchestrator import run_chat

    req = ChatRequest(customer_id=q["customer_id"], persona=q["persona"], locale=q["locale"], messages=[{"role": "user", "content": q["question"]}])
    trace: dict[str, Any] = {}
    text, done, errors, widgets, labels = "", None, [], [], []
    t0 = time.perf_counter()
    async for e in run_chat(req, trace=trace):
        if e.event == "token":
            text += e.data["text"]
        elif e.event == "done":
            done = e.data
        elif e.event == "error":
            errors.append(e.data.get("message"))
        elif e.event == "widget":
            widgets.append(e.data["type"])
        elif e.event == "status":
            labels.append(e.data.get("label", ""))
    elapsed = time.perf_counter() - t0
    results = trace.get("results", [])
    tools = [name for name, _ in results]
    offline = trace.get("mode") == "offline"
    sources: list[Any] = [r.llm_payload for _, r in results]
    if offline:
        sources += [r.raw for _, r in results if r.raw is not None]
    report = check_grounding(text, sources, question=q["question"] + "\n" + trace.get("context", ""), locale=q.get("expect_lang", q["locale"]))
    words = len(re.findall(r"\w+", text))
    checks = {
        "tools": any(t in tools for t in q["expect_tools"]),
        "grounded": report.ok,
        "short": words <= 150,
        "clean": bool(text.strip()) and not errors and not LEAK_MARKERS.search(text),
        "done": bool(done) and len(done.get("suggestions", [])) == 3 and done.get("mood") in MOODS and "sources" in done,
        "lang": detect_language(text, q["locale"]) == q.get("expect_lang", q["locale"]),
        "human": not ANIMAL_WORDS.search(text + "\n" + "\n".join(labels)),
    }
    return {
        "id": q["id"],
        "mode": trace.get("mode"),
        "ok": all(checks.values()),
        "checks": checks,
        "tools": tools,
        "widgets": widgets,
        "ungrounded": report.ungrounded,
        "words": words,
        "seconds": round(elapsed, 1),
        "answer": text,
        "mood": (done or {}).get("mood"),
    }


def print_table(rows: list[dict[str, Any]], show: bool) -> None:
    cols = ["tools", "grounded", "short", "clean", "done", "lang", "human"]
    header = f"{'id':<20} {'mode':<8} " + " ".join(f"{c:<8}" for c in cols) + f" {'words':>5} {'sec':>5}  tools called"
    print(header)
    print("-" * len(header))
    for r in rows:
        marks = " ".join(f"{('PASS' if r['checks'][c] else 'FAIL'):<8}" for c in cols)
        print(f"{r['id']:<20} {r['mode'] or '-':<8} {marks} {r['words']:>5} {r['seconds']:>5}  {','.join(r['tools']) or '-'}")
        if r["ungrounded"]:
            print(f"{'':<29}ungrounded numbers: {r['ungrounded']}")
        if show:
            for line in r["answer"].strip().splitlines():
                print(f"{'':<4}│ {line}")
            print()
    passed = sum(r["ok"] for r in rows)
    print("-" * len(header))
    print(f"{passed}/{len(rows)} questions passed all checks")
    for c in cols:
        n = sum(r["checks"][c] for r in rows)
        print(f"  {c:<9} {n}/{len(rows)}")


async def main_async(args: argparse.Namespace) -> int:
    if args.offline:
        os.environ["LLM_OFFLINE"] = "1"
    only = set(args.only.split(",")) if args.only else None
    questions = load_questions(only)
    rows = []
    for q in questions:
        row = await run_one(q)
        rows.append(row)
        if args.verbose:
            print(f"[{row['id']}] {'ok' if row['ok'] else 'FAIL'} {row['seconds']}s", file=sys.stderr)
    print_table(rows, args.show)
    if args.json:
        Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if args.strict and not all(r["ok"] for r in rows) else 0


def main() -> None:
    import logging

    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="SPankkiBot agent evals")
    parser.add_argument("--offline", action="store_true", help="force the rule-based fallback (LLM_OFFLINE=1)")
    parser.add_argument("--only", help="comma-separated question ids")
    parser.add_argument("--show", action="store_true", help="print every answer")
    parser.add_argument("--json", help="write detailed results to this file")
    parser.add_argument("--strict", action="store_true", help="exit 1 if any question fails")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
