"""Seeding of the demo goals, including the one-time top-up for stores seeded before Joni."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app import store
from app.config import settings


def _use(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "state.db"
    monkeypatch.setattr(settings, "state_db", path)
    store._initialised.discard(str(path))
    return path


def _restart(path: Path) -> None:
    """Forget the in-process 'already initialised' marker so the next call runs init again."""
    store._initialised.discard(str(path))


def _legacy_store(path: Path) -> None:
    """A state.db as written before Joni existed: seeded_v1, old goals, no seeded_v2."""
    conn = sqlite3.connect(path)
    conn.executescript(store.SCHEMA)
    conn.execute(
        "INSERT INTO goals (id, customer_id, name, emoji, kind, target_amount, saved_amount,"
        " deadline, monthly_contribution, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("g_old", "CUST05020", "Emergency fund", "🛟", "emergency", 1500, 420, "2027-06-30", 180, "2026-01-01"),
    )
    conn.execute("INSERT INTO meta (key, value) VALUES ('seeded_v1', '2026-01-01')")
    conn.commit()
    conn.close()


def test_fresh_store_seeds_joni_once(tmp_path, monkeypatch) -> None:
    path = _use(tmp_path, monkeypatch)
    assert store.goal_count("CUST05014") == 1
    rows = store.goal_rows("CUST05014")
    assert (rows[0]["name"], rows[0]["target_amount"], rows[0]["saved_amount"]) == ("Back in the black", 784.58, 0)
    _restart(path)
    assert store.goal_count("CUST05014") == 1  # restart does not duplicate
    with store.connect() as c:
        assert c.execute("SELECT value FROM meta WHERE key = 'seeded_v2'").fetchone() is not None


def test_deleted_goal_stays_deleted(tmp_path, monkeypatch) -> None:
    path = _use(tmp_path, monkeypatch)
    gid = store.goal_rows("CUST05014")[0]["id"]
    assert store.delete_goal_row("CUST05014", gid)
    _restart(path)
    assert store.goal_count("CUST05014") == 0


def test_legacy_store_gets_only_the_new_goal(tmp_path, monkeypatch) -> None:
    path = _use(tmp_path, monkeypatch)
    _legacy_store(path)
    assert store.goal_count("CUST05014") == 1
    assert store.goal_count("CUST05020") == 1  # the user's existing goal is untouched
    assert store.goal_rows("CUST05020")[0]["id"] == "g_old"
    _restart(path)
    assert store.goal_count("CUST05014") == 1  # migration runs once
