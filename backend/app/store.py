"""SQLite store for state the *user* owns: savings goals, chat feedback, linked accounts.

Why SQLite (and not DuckDB)
---------------------------
The analytical DuckDB database is a read-only, content-addressed cache of the bank ledger.
User-created state is tiny, transactional and must survive restarts, which is exactly
what SQLite is for (zero setup, one file: ``backend/state.db``, overridable with
``STATE_DB``). In S-mobiili this module maps 1:1 to a small goals/feedback service.

Concurrency: a new ``sqlite3`` connection is opened per call (cheap) and the database
runs in WAL mode, so FastAPI's thread pool *and* several uvicorn workers can read while
one writes. A writer that finds the file locked waits up to ``SQLITE_BUSY_TIMEOUT_MS``
(5 s) instead of failing. Nothing from this store is cached in memory, so a goal changed
through one worker is visible to the other at once.

Seeding: the first time the store is initialised, every demo customer (SPEC §1.1) gets one
or two goals with partial progress. A ``meta`` flag records that seeding happened, so a goal
the user deletes stays deleted. A store seeded before Joni existed gets his goal in a one-time
top-up transaction (its own flag), so restarts never duplicate it. The check and the inserts
run in one ``BEGIN IMMEDIATE`` transaction, so two workers starting together cannot both seed.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from app.config import settings

_init_lock = threading.Lock()
_initialised: set[str] = set()

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    name TEXT NOT NULL,
    emoji TEXT,
    kind TEXT NOT NULL DEFAULT 'other',
    target_amount REAL NOT NULL,
    saved_amount REAL NOT NULL DEFAULT 0,
    deadline TEXT,
    monthly_contribution REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS goals_customer ON goals(customer_id);
CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    customer_id TEXT,
    persona TEXT,
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    comment TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS linked_accounts (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    label TEXT,
    created_at TEXT NOT NULL
);
"""

#: Seed goals per demo customer: (name, emoji, kind, target, saved, deadline).
SEED_GOALS: dict[str, list[tuple[str, str, str, float, float, str]]] = {
    # Monthly contributions are derived from the deadlines. They fit the real surplus of
    # Emma, Sanna and Pirjo; Leo and Mika overspend, so their seeded goals need more than
    # they have left over (the goal nudge and the planner say so instead of "on track").
    "CUST05020": [("Emergency fund", "🛟", "emergency", 1500, 420, "2027-06-30"),
                  ("New laptop", "💻", "gadget", 1200, 300, "2027-03-31")],
    "CUST00584": [("Emergency fund", "🛟", "emergency", 1000, 80, "2027-09-30"),
                  ("Summer trip", "✈️", "travel", 900, 150, "2027-06-01")],
    "CUST00586": [("Emergency fund", "🛟", "emergency", 10000, 6200, "2027-06-30"),
                  ("Electric car", "🚗", "car", 15000, 3500, "2028-06-30")],
    "CUST00961": [("Emergency fund", "🛟", "emergency", 5000, 4100, "2026-12-31"),
                  ("Home down payment", "🏡", "home", 40000, 26000, "2027-09-30")],
    "CUST00001": [("Emergency fund", "🛟", "emergency", 6000, 5400, "2027-03-31"),
                  ("Trip with the grandkids", "🧳", "travel", 3000, 1200, "2027-12-31")],
    # Joni's balance is negative at the start; the goal pulls it back to zero. It is not a
    # loan repayment and promises no schedule.
    "CUST05014": [("Back in the black", "🎯", "other", 784.58, 0, "2027-09-18")],
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def months_between(start: date, end: date) -> int:
    """Whole monthly contributions that fit between ``start`` and ``end`` (at least 1).

    2026-09-18 → 2027-03-31 = 6, 2026-09-18 → 2026-10-10 = 1 (minimum)."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(1, months)


def _path() -> Path:
    return Path(settings.state_db)


def _open(path: Path) -> sqlite3.Connection:
    busy_ms = max(0, int(settings.sqlite_busy_timeout_ms))
    conn = sqlite3.connect(path, timeout=busy_ms / 1000)
    conn.execute(f"PRAGMA busy_timeout = {busy_ms}")
    conn.execute("PRAGMA synchronous = NORMAL")  # safe with WAL, far fewer fsyncs
    return conn


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Per-call SQLite connection with dict rows; commits on success."""
    path = _path()
    _ensure_init(path)
    conn = _open(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _ensure_init(path: Path) -> None:
    key = str(path)
    if key in _initialised:
        return
    with _init_lock:
        if key in _initialised:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        # Two workers start at the same moment on first boot. Switching a new file to WAL
        # needs an exclusive lock and SQLite does not apply the busy timeout to that step,
        # so the losing worker retries instead of crashing on "database is locked".
        deadline = time.monotonic() + max(5.0, settings.sqlite_busy_timeout_ms / 1000)
        while True:
            try:
                _init_schema_and_seed(path)
                break
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        _initialised.add(key)


def _insert_seed_goals(conn: sqlite3.Connection, customer_id: str,
                       goals: list[tuple[str, str, str, float, float, str]]) -> None:
    """Insert one customer's seed goals (caller owns the transaction)."""
    as_of = settings.as_of_date
    for name, emoji, kind, target, saved, deadline in goals:
        months = months_between(as_of, date.fromisoformat(deadline))
        conn.execute(
            "INSERT INTO goals (id, customer_id, name, emoji, kind, target_amount,"
            " saved_amount, deadline, monthly_contribution, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (f"g_{uuid.uuid4().hex[:10]}", customer_id, name, emoji, kind, target, saved,
             deadline, round((target - saved) / months, 2), _now()),
        )


def _init_schema_and_seed(path: Path) -> None:
    """Create the tables and seed the demo goals once. Safe to repeat and to run concurrently."""
    conn = _open(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.isolation_level = None  # explicit transaction below
        conn.execute("BEGIN IMMEDIATE")  # one worker at a time: no double seeding
        seeded = conn.execute("SELECT value FROM meta WHERE key = 'seeded_v1'").fetchone()
        if not seeded:
            for cid, goals in SEED_GOALS.items():
                _insert_seed_goals(conn, cid, goals)
            conn.execute("INSERT INTO meta (key, value) VALUES ('seeded_v1', ?)", (_now(),))
            # A fresh store already has the late additions, so record the top-up as done.
            conn.execute("INSERT INTO meta (key, value) VALUES ('seeded_v2', ?)", (_now(),))
        elif not conn.execute("SELECT value FROM meta WHERE key = 'seeded_v2'").fetchone():
            # One-time top-up for stores seeded before Joni was added. The flag keeps a goal
            # the user deleted from coming back on the next restart.
            _insert_seed_goals(conn, "CUST05014", SEED_GOALS["CUST05014"])
            conn.execute("INSERT INTO meta (key, value) VALUES ('seeded_v2', ?)", (_now(),))
        conn.execute("COMMIT")
    finally:
        conn.close()


# ----------------------------------------------------------------------------- goals
def goal_rows(customer_id: str) -> list[dict[str, Any]]:
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM goals WHERE customer_id = ? ORDER BY created_at, rowid", (customer_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def goal_count(customer_id: str) -> int:
    with connect() as c:
        return int(c.execute("SELECT count(*) FROM goals WHERE customer_id = ?", (customer_id,)).fetchone()[0])


def goal_row(customer_id: str, goal_id: str) -> dict[str, Any] | None:
    with connect() as c:
        r = c.execute("SELECT * FROM goals WHERE customer_id = ? AND id = ?",
                      (customer_id, goal_id)).fetchone()
    return dict(r) if r else None


def insert_goal(row: dict[str, Any]) -> dict[str, Any]:
    row = {**row, "id": row.get("id") or f"g_{uuid.uuid4().hex[:10]}", "created_at": _now()}
    cols = ("id", "customer_id", "name", "emoji", "kind", "target_amount", "saved_amount",
            "deadline", "monthly_contribution", "created_at")
    with connect() as c:
        c.execute(f"INSERT INTO goals ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                  tuple(row.get(k) for k in cols))
    return row


GOAL_MUTABLE = ("name", "emoji", "kind", "target_amount", "saved_amount", "deadline",
                "monthly_contribution")


def update_goal_row(customer_id: str, goal_id: str, fields: dict[str, Any]) -> bool:
    sets = {k: v for k, v in fields.items() if k in GOAL_MUTABLE}
    if not sets:
        return goal_row(customer_id, goal_id) is not None
    assignments = ", ".join(f"{k} = ?" for k in sets)  # keys come from the whitelist above
    with connect() as c:
        cur = c.execute(f"UPDATE goals SET {assignments} WHERE customer_id = ? AND id = ?",
                        (*sets.values(), customer_id, goal_id))
        return cur.rowcount > 0


def delete_goal_row(customer_id: str, goal_id: str) -> bool:
    with connect() as c:
        cur = c.execute("DELETE FROM goals WHERE customer_id = ? AND id = ?", (customer_id, goal_id))
        return cur.rowcount > 0


# -------------------------------------------------------------------------- feedback
def save_feedback(message_id: str, rating: int, comment: str | None = None,
                  customer_id: str | None = None, persona: str | None = None) -> dict[str, Any]:
    """Persist a 👍/👎 on an assistant message (used by POST /api/chat/feedback)."""
    if rating not in (1, -1):
        raise ValueError("rating must be 1 or -1")
    with connect() as c:
        cur = c.execute(
            "INSERT INTO feedback (message_id, customer_id, persona, rating, comment, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (message_id, customer_id, persona, rating, comment, _now()),
        )
        fid = cur.lastrowid
    return {"id": fid, "message_id": message_id, "rating": rating, "ok": True}


def feedback_summary() -> dict[str, Any]:
    """Aggregate thumbs up/down (for the evals dashboard)."""
    with connect() as c:
        r = c.execute("SELECT count(*) AS n, coalesce(sum(rating = 1), 0) AS up,"
                      " coalesce(sum(rating = -1), 0) AS down FROM feedback").fetchone()
    return dict(r)


# ------------------------------------------------------------------- linked accounts
def list_linked_accounts(customer_id: str) -> list[dict[str, Any]]:
    """External accounts a user linked via PSD2/MyData consent (placeholder data model)."""
    with connect() as c:
        rows = c.execute("SELECT * FROM linked_accounts WHERE customer_id = ?",
                         (customer_id,)).fetchall()
    return [dict(r) for r in rows]


def add_linked_account(customer_id: str, provider: str, label: str | None = None) -> dict[str, Any]:
    row = {"id": f"la_{uuid.uuid4().hex[:10]}", "customer_id": customer_id,
           "provider": provider, "label": label, "created_at": _now()}
    with connect() as c:
        c.execute("INSERT INTO linked_accounts (id, customer_id, provider, label, created_at)"
                  " VALUES (:id, :customer_id, :provider, :label, :created_at)", row)
    return row
