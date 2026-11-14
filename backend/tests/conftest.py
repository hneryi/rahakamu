"""Test configuration.

* User state (goals, feedback) goes to a throw-away SQLite file so tests never touch
  ``backend/state.db``; the env var must be set *before* ``app.config`` is imported.
* The DuckDB ledger cache is shared with the dev server (it is read-only and
  content-addressed), so only the very first run pays the ~8 s build.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="spankkibot-tests-"))
os.environ["STATE_DB"] = str(_TMP / "state.db")

DEMO_IDS = ["CUST05020", "CUST00584", "CUST00586", "CUST00961", "CUST00001", "CUST05014"]


@pytest.fixture(scope="session")
def client() -> Iterator["TestClient"]:  # noqa: F821
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        # The app warms the ledger cache in a background thread so that /api/health can
        # answer at once; tests want the data loaded before the first assertion.
        from app import db

        db.get_conn()
        yield c


@pytest.fixture(params=DEMO_IDS)
def demo_id(request: pytest.FixtureRequest) -> str:
    return str(request.param)
