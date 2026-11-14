"""DuckDB data layer: one in-memory analytical database shared by the whole API.

Why it is built this way
------------------------
* **DuckDB, in-process.** The challenge dataset is 3.6 M transactions in a 60 MB Parquet
  file. DuckDB reads it columnar and vectorised with zero infrastructure, which keeps the
  project *feasible* (one ``uv run`` and you are live) and *portable* (the same SQL runs on
  MotherDuck / a warehouse inside S-Bank later).
* **Materialise once, query many.** On first use we load the Parquet into an in-memory
  table ``tx`` that is (1) cut at ``AS_OF_DATE`` so nothing "from the future" leaks into
  any number, (2) sorted by ``customer_id`` so DuckDB's zone maps turn every
  ``WHERE customer_id = ?`` into a tiny range scan (single-digit milliseconds), and
  (3) enriched with the derived columns every feature needs: a stable transaction ``id``,
  the recurring-payment flag, the essential-outlier flag and the **basket** (computed by
  the single source-of-truth expression :func:`app.analytics.baskets.classify_sql`).
* **Build once per data version.** Materialising takes a few seconds, so the result is
  persisted to ``backend/.cache/spankki_<key>.duckdb`` and opened **read-only** by every
  later process (uvicorn workers, pytest, the eval runner can share it concurrently). The
  cache key hashes the AS_OF date, the Parquet file's size/mtime and the basket rules
  text, so changing a classification rule automatically triggers a rebuild.
* **Per-customer slices (< 300 ms per request).** Even with zone maps, every query on the
  3.6 M-row table scans one 122 880-row group (~7 ms), and the home screen runs ~40 small
  queries. So the first time a customer is touched, their ~700 rows are copied into a
  private schema ``s_<customer_id>`` of the in-memory database (LRU, 1 024 customers).
  Every query written as ``... FROM tx WHERE customer_id = ? ...`` with the customer id as
  the first parameter is transparently run with ``search_path`` pointing at that slice,
  so analytics SQL stays plain and readable, yet runs in well under a millisecond.
* **Thread safety.** FastAPI runs sync endpoints in a thread pool. A DuckDB connection
  must not be shared across threads, but ``connection.cursor()`` creates a cheap child
  connection to the same database, so every helper below opens its own cursor per call
  (``search_path`` is per cursor, so slices never leak between requests).
* **Safety.** All helpers take bound parameters (``?``); analytics modules never format
  user input into SQL. Column / group-by names are chosen from whitelists in code.

Tables / views created
----------------------
``tx``                enriched transactions (≤ AS_OF), see :data:`TX_COLUMNS`
``customers``         customer_id, postal_code (VARCHAR, leading zeros kept), age
``mortgages``         final mortgage outcome per applicant (200 rows)
``mortgage_events``   negotiation history with parsed timestamps
``peer_category``     per customer × category: average monthly spend (last 6 full months)
``peer_flows``        per customer: average monthly income / spending / saving + savings rate
``customer_traits``   per customer: raw spending-behaviour traits + their percentile among
                      all customers (feeds the transparent spender profile)
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb

from app.config import BACKEND_DIR, settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_conn: duckdb.DuckDBPyConnection | None = None

#: Columns of the enriched ``tx`` table (documented for analytics authors).
TX_COLUMNS: tuple[str, ...] = (
    "id",  # stable synthetic id 'tx_<n>' (dataset has no tx id)
    "customer_id",
    "tx_date",
    "tx_timestamp",
    "category",
    "tx_amount_eur",  # negative = money out
    "balance_after_eur",
    "transaction_type",
    "merchant_id",
    "mcc_code",
    "is_recurring",  # merchant stream with ~monthly cadence and stable amount (CV < 0.25)
    "is_outlier",  # one-off large purchase in an essential category
    "basket",  # fixed | irregular | leak | income | saving
)


class CustomerNotFound(KeyError):
    """Raised when a customer id is not in the dataset (routers map it to HTTP 404)."""


def _csv(path: Path, types: dict[str, str] | None = None) -> str:
    """DuckDB ``read_csv`` call for one of the challenge CSVs.

    The files start with a UTF-8 BOM; DuckDB's sniffer strips it from the header. ``types``
    pins columns (e.g. ``customer_postal_code`` → VARCHAR so ``00990`` keeps its zeros).
    """
    p = str(path).replace("'", "''")
    opts = ""
    if types:
        opts = ", types={" + ", ".join(f"'{k}': '{v}'" for k, v in types.items()) + "}"
    return f"read_csv('{p}', header=true, encoding='utf-8'{opts})"


def _build(conn: duckdb.DuckDBPyConnection) -> None:
    """Create and populate all tables (≈5 s; runs only when the cache key changes)."""
    from app.analytics.baskets import classify_sql  # local import: avoids an import cycle

    data = settings.data_dir
    parquet = data / "transactions.parquet"
    if not parquet.exists():
        raise FileNotFoundError(
            f"{parquet} not found. Put the challenge data in DATA_DIR (see README)."
        )
    as_of = settings.as_of_date.isoformat()
    t0 = time.perf_counter()

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE customers AS
        SELECT customer_id,
               CAST(customer_postal_code AS VARCHAR) AS postal_code,
               CAST(customer_age AS INTEGER) AS age
        FROM {_csv(data / 'tx_customers_junction.csv', {'customer_postal_code': 'VARCHAR', 'customer_id': 'VARCHAR'})}
        """
    )

    mtg_link = data / "mtg_tx_customer_link_and_final_mtg_infio.csv"
    if mtg_link.exists():
        conn.execute(f"CREATE OR REPLACE TABLE mortgages AS SELECT * FROM {_csv(mtg_link)}")
    else:  # mortgage features degrade gracefully without the file
        conn.execute(
            "CREATE OR REPLACE TABLE mortgages (mortgage_customer_id VARCHAR, customer_id VARCHAR,"
            " final_decision VARCHAR, rejection_reason VARCHAR, final_property_price_eur DOUBLE,"
            " final_requested_loan_eur DOUBLE, final_equity_amount_eur DOUBLE,"
            " final_collateral_value_eur DOUBLE, required_monthly_income_eur DOUBLE,"
            " lfinal_loan_to_value DOUBLE)"
        )
    mtg_hist = data / "mtg_negotiation_history.csv"
    if mtg_hist.exists():
        conn.execute(
            f"""
            CREATE OR REPLACE TABLE mortgage_events AS
            SELECT * EXCLUDE (timestamp),
                   try_strptime(CAST(timestamp AS VARCHAR), '%d%b%y:%H:%M:%S') AS ts
            FROM read_csv('{str(mtg_hist).replace("'", "''")}', header=true, all_varchar=true)
            """
        )
    else:
        conn.execute(
            "CREATE OR REPLACE TABLE mortgage_events (mortgage_customer_id VARCHAR,"
            " event_type VARCHAR, note VARCHAR, ts TIMESTAMP)"
        )

    # Enriched transactions. Window/aggregate steps:
    #   streams   – per (customer, merchant): cadence (median gap), amount CV, months seen
    #   recurring – stream qualifies as a subscription-like monthly payment
    #   medians   – per (customer, category) typical ticket, for one-off outlier detection
    p = str(parquet).replace("'", "''")
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE tx AS
        WITH raw AS (
            SELECT * FROM read_parquet('{p}') WHERE tx_date <= DATE '{as_of}'
        ),
        gaps AS (
            SELECT customer_id, merchant_id, tx_amount_eur,
                   date_diff('day', lag(tx_date) OVER (PARTITION BY customer_id, merchant_id
                                                       ORDER BY tx_timestamp), tx_date) AS gap,
                   strftime(tx_date, '%Y-%m') AS ym
            FROM raw WHERE merchant_id IS NOT NULL AND tx_amount_eur < 0
        ),
        streams AS (
            SELECT customer_id, merchant_id,
                   count(*) AS n, count(DISTINCT ym) AS months,
                   median(gap) AS med_gap,
                   stddev_samp(tx_amount_eur) / nullif(abs(avg(tx_amount_eur)), 0) AS cv
            FROM gaps GROUP BY ALL
        ),
        recurring AS (
            SELECT customer_id, merchant_id FROM streams
            WHERE n >= 4 AND months >= 4 AND med_gap BETWEEN 25 AND 35 AND coalesce(cv, 0) < 0.25
        ),
        medians AS (
            SELECT customer_id, category, median(-tx_amount_eur) AS med
            FROM raw WHERE tx_amount_eur < 0 GROUP BY ALL
        ),
        enriched AS (
            SELECT r.*,
                   (rc.merchant_id IS NOT NULL) AS is_recurring,
                   (r.tx_amount_eur < 0
                    AND r.category IN ('Groceries', 'Transportation', 'Utilities')
                    AND -r.tx_amount_eur > greatest(3 * m.med, 120)) AS is_outlier
            FROM raw r
            LEFT JOIN recurring rc USING (customer_id, merchant_id)
            LEFT JOIN medians m USING (customer_id, category)
        )
        SELECT 'tx_' || CAST(row_number() OVER (ORDER BY customer_id, tx_timestamp, tx_amount_eur)
                              AS VARCHAR) AS id,
               customer_id, tx_date, tx_timestamp, category, tx_amount_eur, balance_after_eur,
               transaction_type, merchant_id, mcc_code, is_recurring, is_outlier,
               {classify_sql()} AS basket
        FROM enriched
        ORDER BY customer_id, tx_timestamp
        """
    )
    # Peer statistics for benchmarks: last 6 complete months before the as-of month.
    from app.analytics.common import add_months, month_start

    first_cur = month_start(settings.as_of_date)
    p_start, p_end = add_months(first_cur, -6).isoformat(), first_cur.isoformat()
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE peer_category AS
        SELECT customer_id, category, sum(-tx_amount_eur) / 6.0 AS monthly
        FROM tx
        WHERE tx_date >= DATE '{p_start}' AND tx_date < DATE '{p_end}'
          AND tx_amount_eur < 0 AND basket IN ('fixed', 'irregular', 'leak')
        GROUP BY ALL
        """
    )
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE peer_flows AS
        SELECT c.customer_id, c.age,
               coalesce(sum(CASE WHEN basket = 'income' THEN tx_amount_eur END), 0) / 6.0 AS income,
               coalesce(sum(CASE WHEN basket IN ('fixed','irregular','leak')
                                 THEN -tx_amount_eur END), 0) / 6.0 AS spending,
               coalesce(sum(CASE WHEN basket = 'saving' THEN -tx_amount_eur END), 0) / 6.0 AS saving
        FROM customers c
        LEFT JOIN tx ON tx.customer_id = c.customer_id
             AND tx_date >= DATE '{p_start}' AND tx_date < DATE '{p_end}'
        GROUP BY ALL
        """
    )
    # Behaviour traits (same 6-month window). Percentiles make every score explainable:
    # "you make more small leak purchases than 82 % of customers".
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE customer_traits AS
        WITH w AS (
            SELECT * FROM tx WHERE tx_date >= DATE '{p_start}' AND tx_date < DATE '{p_end}'
        ),
        monthly AS (
            SELECT customer_id, strftime(tx_date, '%Y-%m') AS ym, sum(-tx_amount_eur) AS spent
            FROM w WHERE basket IN ('fixed','irregular','leak') GROUP BY ALL
        ),
        vol AS (
            SELECT customer_id, stddev_pop(spent) / nullif(avg(spent), 0) AS volatility
            FROM monthly GROUP BY ALL
        ),
        daily AS (
            SELECT customer_id, tx_date, arg_max(balance_after_eur, tx_timestamp) AS eod
            FROM w GROUP BY ALL
        ),
        cushion AS (
            SELECT customer_id, count(*) FILTER (WHERE eod < 0) AS days_below_zero,
                   min(eod) AS min_balance, avg(eod) AS avg_balance
            FROM daily GROUP BY ALL
        ),
        raw AS (
            SELECT customer_id,
                   sum(CASE WHEN basket = 'income' THEN tx_amount_eur ELSE 0 END) AS income,
                   sum(CASE WHEN basket IN ('fixed','irregular','leak') THEN -tx_amount_eur ELSE 0 END) AS spend,
                   sum(CASE WHEN basket = 'leak' THEN -tx_amount_eur ELSE 0 END) AS leak,
                   sum(CASE WHEN basket = 'leak' AND isodow(tx_date) IN (5, 6, 7)
                            THEN -tx_amount_eur ELSE 0 END) AS leak_weekend,
                   count(*) FILTER (WHERE basket = 'leak' AND tx_amount_eur > -15) AS small_leaks,
                   count(*) FILTER (WHERE basket = 'leak' AND tx_amount_eur < -100) AS big_leaks,
                   count(*) FILTER (WHERE tx_amount_eur < 0 AND basket <> 'saving'
                                    AND (hour(tx_timestamp) >= 22 OR hour(tx_timestamp) < 5)) AS late_tx,
                   count(*) FILTER (WHERE tx_amount_eur < 0 AND basket <> 'saving') AS out_tx
            FROM w GROUP BY ALL
        ),
        t AS (
            SELECT r.customer_id,
                   CASE WHEN income > 0 THEN 1 - spend / income ELSE -1 END AS savings_rate,
                   CASE WHEN spend > 0 THEN leak / spend ELSE 0 END AS leak_share,
                   CASE WHEN leak > 0 THEN leak_weekend / leak ELSE 0 END AS weekend_share,
                   small_leaks * 7.0 / {(date.fromisoformat(p_end) - date.fromisoformat(p_start)).days}
                       AS small_tx_per_week,
                   big_leaks / 6.0 AS big_leaks_per_month,
                   CASE WHEN out_tx > 0 THEN late_tx / out_tx ELSE 0 END AS late_night_share,
                   coalesce(v.volatility, 0) AS volatility,
                   coalesce(c.days_below_zero, 0) AS days_below_zero,
                   coalesce(c.min_balance, 0) AS min_balance,
                   CASE WHEN spend > 0 THEN coalesce(c.min_balance, 0) / (spend / 6.0) ELSE 0 END
                       AS cushion_months
            FROM raw r LEFT JOIN vol v USING (customer_id) LEFT JOIN cushion c USING (customer_id)
        )
        SELECT *,
               round(100 * percent_rank() OVER (ORDER BY savings_rate)) AS p_savings_rate,
               round(100 * percent_rank() OVER (ORDER BY leak_share)) AS p_leak_share,
               round(100 * percent_rank() OVER (ORDER BY weekend_share)) AS p_weekend_share,
               round(100 * percent_rank() OVER (ORDER BY small_tx_per_week)) AS p_small_tx,
               round(100 * percent_rank() OVER (ORDER BY big_leaks_per_month)) AS p_big_leaks,
               round(100 * percent_rank() OVER (ORDER BY late_night_share)) AS p_late_night,
               round(100 * percent_rank() OVER (ORDER BY volatility DESC)) AS p_steadiness,
               round(100 * percent_rank() OVER (ORDER BY cushion_months)) AS p_cushion
        FROM t
        """
    )
    n = conn.execute("SELECT count(*) FROM tx").fetchone()[0]  # type: ignore[index]
    log.info("DuckDB ready: %s tx ≤ %s in %.1fs", n, as_of, time.perf_counter() - t0)


BUILD_VERSION = "4"  # bump when the table layout changes


def _cache_path() -> Path:
    """Content-addressed cache file for the materialised database."""
    from app.analytics.baskets import classify_sql

    parquet = settings.data_dir / "transactions.parquet"
    st = parquet.stat()
    key = "|".join([BUILD_VERSION, settings.as_of_date.isoformat(), str(parquet.resolve()),
                    str(st.st_size), str(int(st.st_mtime)), classify_sql()])
    digest = hashlib.sha256(key.encode()).hexdigest()[:16]
    return BACKEND_DIR / ".cache" / f"spankki_{digest}.duckdb"


def _ensure_cache() -> Path:
    """Build the materialised cache file for this data version if it does not exist yet."""
    path = _cache_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.unlink(missing_ok=True)
    build = duckdb.connect(str(tmp))
    build.execute("SET enable_progress_bar = false")
    try:
        _build(build)
        build.execute("CHECKPOINT")
    finally:
        build.close()
    os.replace(tmp, path)  # atomic: concurrent builders never see half a file
    for old in path.parent.glob("spankki_*.duckdb"):  # drop stale versions
        if old != path:
            old.unlink(missing_ok=True)
    return path


def get_conn() -> duckdb.DuckDBPyConnection:
    """Process-wide in-memory DuckDB with the cache file attached read-only as ``cache``.

    Several processes (uvicorn, pytest, eval runner) can attach the same cache at once.
    """
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                path = _ensure_cache()
                conn = duckdb.connect(database=":memory:")
                conn.execute("SET enable_progress_bar = false")
                conn.execute("SET threads TO 2")  # tiny queries: fewer threads = less overhead
                safe = str(path).replace("'", "''")
                conn.execute(f"ATTACH '{safe}' AS cache (READ_ONLY)")
                _conn = conn
    return _conn


# --------------------------------------------------------------------------- readiness
_warm_lock = threading.Lock()
_warm_thread: threading.Thread | None = None
_warm_error: str | None = None


def is_ready() -> bool:
    """True once the cache is attached. Never blocks (unlike ``get_conn``)."""
    return _conn is not None


def _warm() -> None:
    global _warm_error
    try:
        get_conn()
        _warm_error = None
    except Exception as exc:  # noqa: BLE001 - reported by /api/health, retried on next call
        _warm_error = type(exc).__name__
        log.exception("Data warm-up failed")


def start_warmup() -> None:
    """Load (or, on first boot, build) the cache in a background thread. Idempotent.

    Called at startup and by the health endpoint, so a failed build is retried the next
    time anyone asks, without ever making the health check itself wait.
    """
    global _warm_thread
    if _conn is not None:
        return
    with _warm_lock:
        if _warm_thread is not None and _warm_thread.is_alive():
            return
        _warm_thread = threading.Thread(target=_warm, name="duckdb-warmup", daemon=True)
        _warm_thread.start()


def readiness() -> str:
    """``ready`` | ``loading`` | ``error`` (the last warm-up failed). Never blocks."""
    if _conn is not None:
        return "ready"
    if _warm_thread is not None and _warm_thread.is_alive():
        return "loading"
    return "error" if _warm_error else "loading"


# ---------------------------------------------------------------- per-customer slices
_SLICE_MAX = 1024
_slices: OrderedDict[str, str] = OrderedDict()
_slice_lock = threading.Lock()
_SLICE_SQL = re.compile(r"\bFROM\s+tx\s+WHERE\s+customer_id\s*=\s*\?", re.IGNORECASE)
_SCHEMA_SAFE = re.compile(r"[^A-Za-z0-9]")
_BASE_PATH = "SET search_path = 'cache.main'"


def _slice_schema(customer_id: str) -> str:
    """Schema holding this customer's rows, creating it on first use (LRU-evicted)."""
    schema = _slices.get(customer_id)
    if schema is not None:
        _slices.move_to_end(customer_id)
        return schema
    with _slice_lock:
        schema = _slices.get(customer_id)
        if schema is None:
            schema = "s_" + _SCHEMA_SAFE.sub("_", customer_id)
            cur = get_conn().cursor()
            try:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS memory.{schema}")
                cur.execute(
                    f"CREATE OR REPLACE TABLE memory.{schema}.tx AS "
                    "SELECT * FROM cache.main.tx WHERE customer_id = ? ORDER BY tx_timestamp",
                    [customer_id],
                )
                _slices[customer_id] = schema
                while len(_slices) > _SLICE_MAX:
                    _, old = _slices.popitem(last=False)
                    cur.execute(f"DROP SCHEMA IF EXISTS memory.{old} CASCADE")
            finally:
                cur.close()
    return schema


def cursor(customer_id: str | None = None) -> duckdb.DuckDBPyConnection:
    """A fresh per-call cursor. With ``customer_id`` unqualified ``tx`` resolves to that
    customer's slice; other tables always resolve to the attached cache."""
    cur = get_conn().cursor()
    if customer_id is None:
        cur.execute(_BASE_PATH)
    else:
        cur.execute(f"SET search_path = 'memory.{_slice_schema(customer_id)},cache.main'")
    return cur


def _route(sql: str, params: Sequence[Any] | None) -> str | None:
    """Customer id to route to, if the query follows the slice convention."""
    if params and isinstance(params[0], str) and _SLICE_SQL.search(sql):
        return params[0]
    return None


def query(sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    """Run parameterised SQL and return rows as dicts."""
    cur = cursor(_route(sql, params))
    try:
        res = cur.execute(sql, list(params or []))
        cols = [d[0] for d in res.description]
        return [dict(zip(cols, row, strict=True)) for row in res.fetchall()]
    finally:
        cur.close()


def query_one(sql: str, params: Sequence[Any] | None = None) -> dict[str, Any] | None:
    """First row as dict, or ``None``."""
    rows = query(sql, params)
    return rows[0] if rows else None


def scalar(sql: str, params: Sequence[Any] | None = None) -> Any:
    """First column of the first row (``None`` if no rows)."""
    cur = cursor(_route(sql, params))
    try:
        row = cur.execute(sql, list(params or [])).fetchone()
        return row[0] if row else None
    finally:
        cur.close()


@lru_cache(maxsize=8192)
def _customer_row(customer_id: str) -> tuple[str, str, int] | None:
    row = query_one(
        "SELECT customer_id, postal_code, age FROM customers WHERE customer_id = ?",
        [customer_id],
    )
    return (row["customer_id"], row["postal_code"], int(row["age"])) if row else None


def get_customer(customer_id: str) -> dict[str, Any]:
    """Customer master row or :class:`CustomerNotFound` (cached; the data is immutable)."""
    if not isinstance(customer_id, str) or not customer_id:
        raise CustomerNotFound(customer_id)
    row = _customer_row(customer_id)
    if row is None:
        raise CustomerNotFound(customer_id)
    return {"customer_id": row[0], "postal_code": row[1], "age": row[2]}


def ensure_customer(customer_id: str) -> None:
    """Validate a customer id early (cheap; raises :class:`CustomerNotFound`)."""
    get_customer(customer_id)


def as_of() -> date:
    """The simulated 'today'."""
    return settings.as_of_date
