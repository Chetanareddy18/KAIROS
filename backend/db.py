"""Thread-safe DuckDB access shared by every agent.

DuckDB connections must not be used from several threads at once, and FastAPI
serves sync routes from a thread pool while the scheduler runs the pipeline in
another thread. One connection guarded by a re-entrant lock keeps it simple.
"""
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

import duckdb
import pandas as pd

logger = logging.getLogger("kairos.db")

_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS metrics (
        source      VARCHAR     NOT NULL,
        metric_name VARCHAR     NOT NULL,
        timestamp   TIMESTAMPTZ NOT NULL,
        value       DOUBLE      NOT NULL,
        ingested_at TIMESTAMPTZ DEFAULT now(),
        PRIMARY KEY (source, metric_name, timestamp)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        name             VARCHAR PRIMARY KEY,
        type             VARCHAR NOT NULL,
        config           VARCHAR NOT NULL,
        enabled          BOOLEAN DEFAULT TRUE,
        managed_by       VARCHAR DEFAULT 'api',
        description      VARCHAR DEFAULT '',
        created_at       TIMESTAMPTZ DEFAULT now(),
        last_sync        TIMESTAMPTZ,
        last_status      VARCHAR DEFAULT 'never',
        last_error       VARCHAR,
        last_rows        BIGINT DEFAULT 0,
        last_bytes       BIGINT DEFAULT 0,
        last_duration_ms BIGINT DEFAULT 0,
        total_rows       BIGINT DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS connector_state (
        source     VARCHAR PRIMARY KEY,
        state      VARCHAR NOT NULL,
        updated_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    "CREATE SEQUENCE IF NOT EXISTS anomaly_seq",
    """
    CREATE TABLE IF NOT EXISTS anomalies (
        id              BIGINT DEFAULT nextval('anomaly_seq'),
        source          VARCHAR     NOT NULL,
        metric_name     VARCHAR     NOT NULL,
        timestamp       TIMESTAMPTZ NOT NULL,
        observed_value  DOUBLE,
        expected_value  DOUBLE,
        deviation_score DOUBLE,
        severity        VARCHAR,
        method          VARCHAR,
        detected_at     TIMESTAMPTZ DEFAULT now(),
        alerted         BOOLEAN DEFAULT FALSE,
        PRIMARY KEY (source, metric_name, timestamp)
    )
    """,
    "CREATE SEQUENCE IF NOT EXISTS alert_seq",
    """
    CREATE TABLE IF NOT EXISTS alerts (
        id            BIGINT DEFAULT nextval('alert_seq') PRIMARY KEY,
        sent_at       TIMESTAMPTZ DEFAULT now(),
        report        VARCHAR,
        telegram      BOOLEAN,
        email         BOOLEAN,
        anomaly_count INTEGER,
        verified      BOOLEAN,
        model         VARCHAR
    )
    """,
    "CREATE SEQUENCE IF NOT EXISTS run_seq",
    """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        id                BIGINT DEFAULT nextval('run_seq') PRIMARY KEY,
        started_at        TIMESTAMPTZ,
        finished_at       TIMESTAMPTZ,
        trigger           VARCHAR,
        status            VARCHAR,
        metrics_collected BIGINT,
        anomalies_found   INTEGER,
        new_anomalies     INTEGER,
        alert_sent        BOOLEAN,
        errors            VARCHAR,
        result            VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transfers (
        id           VARCHAR PRIMARY KEY,
        filename     VARCHAR NOT NULL,
        size_bytes   BIGINT,
        chunk_size   BIGINT,
        total_chunks INTEGER,
        sha256       VARCHAR,
        compression  VARCHAR,
        source_name  VARCHAR,
        status       VARCHAR,
        bytes_on_wire BIGINT DEFAULT 0,
        created_at   TIMESTAMPTZ DEFAULT now(),
        completed_at TIMESTAMPTZ,
        stored_path  VARCHAR,
        error        VARCHAR
    )
    """,
]


class Database:
    def __init__(self, path: str):
        self.path  = path
        self._lock = threading.RLock()
        self.conn  = duckdb.connect(path)
        self.conn.execute("SET TimeZone = 'UTC'")
        self._migrate_legacy_metrics()
        for stmt in _SCHEMA:
            self.conn.execute(stmt)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics (metric_name, timestamp)"
        )

    # ── low-level helpers ────────────────────────────────────────────────────

    @contextmanager
    def locked(self):
        with self._lock:
            yield self.conn

    def execute(self, sql: str, params: list | None = None):
        with self._lock:
            return self.conn.execute(sql, params or []).fetchall()

    def df(self, sql: str, params: list | None = None) -> pd.DataFrame:
        with self._lock:
            return self.conn.execute(sql, params or []).df()

    def scalar(self, sql: str, params: list | None = None):
        rows = self.execute(sql, params)
        return rows[0][0] if rows else None

    # ── legacy migration ─────────────────────────────────────────────────────

    def _migrate_legacy_metrics(self) -> None:
        """v1 stored metrics without a primary key, so re-runs duplicated rows."""
        exists = self.conn.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'metrics'"
        ).fetchone()[0]
        if not exists:
            return
        has_pk = self.conn.execute(
            "SELECT count(*) FROM duckdb_constraints() "
            "WHERE table_name = 'metrics' AND constraint_type = 'PRIMARY KEY'"
        ).fetchone()[0]
        if has_pk:
            return
        logger.warning("Migrating legacy metrics table (adding primary key, removing duplicates)")
        # DuckDB refuses to rename a table that still has indexes on it
        for (idx,) in self.conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'metrics'"
        ).fetchall():
            self.conn.execute(f'DROP INDEX IF EXISTS "{idx}"')
        self.conn.execute("ALTER TABLE metrics RENAME TO metrics_legacy")
        self.conn.execute(_SCHEMA[0])
        self.conn.execute(
            "INSERT INTO metrics (source, metric_name, timestamp, value) "
            "SELECT source, metric_name, timestamp, last(value) FROM metrics_legacy "
            "GROUP BY source, metric_name, timestamp"
        )
        self.conn.execute("DROP TABLE metrics_legacy")

    # ── metrics ──────────────────────────────────────────────────────────────

    def upsert_metrics(self, df: pd.DataFrame) -> int:
        """Idempotent insert: re-ingesting the same point updates it instead of duplicating."""
        if df is None or df.empty:
            return 0
        batch = (
            df[["source", "metric_name", "timestamp", "value"]]
            .drop_duplicates(subset=["source", "metric_name", "timestamp"], keep="last")
            .reset_index(drop=True)
        )
        with self._lock:
            self.conn.register("_kairos_batch", batch)
            try:
                self.conn.execute(
                    "INSERT INTO metrics (source, metric_name, timestamp, value) "
                    "SELECT source, metric_name, timestamp, value FROM _kairos_batch "
                    "ON CONFLICT (source, metric_name, timestamp) "
                    "DO UPDATE SET value = excluded.value, ingested_at = now()"
                )
            finally:
                self.conn.unregister("_kairos_batch")
        return len(batch)

    # ── connector state (watermarks, processed files, cursors) ───────────────

    def get_state(self, source: str) -> dict:
        raw = self.scalar("SELECT state FROM connector_state WHERE source = ?", [source])
        return json.loads(raw) if raw else {}

    def set_state(self, source: str, state: dict) -> None:
        self.execute(
            "INSERT INTO connector_state (source, state, updated_at) VALUES (?, ?, now()) "
            "ON CONFLICT (source) DO UPDATE SET state = excluded.state, updated_at = now()",
            [source, json.dumps(state, default=str)],
        )

    def clear_state(self, source: str) -> None:
        self.execute("DELETE FROM connector_state WHERE source = ?", [source])

    # ── maintenance ──────────────────────────────────────────────────────────

    def reset(self) -> None:
        with self._lock:
            for table in ("metrics", "anomalies", "alerts", "pipeline_runs", "connector_state"):
                self.conn.execute(f"DELETE FROM {table}")
            self.conn.execute(
                "UPDATE sources SET last_sync = NULL, last_status = 'never', last_error = NULL, "
                "last_rows = 0, last_bytes = 0, last_duration_ms = 0, total_rows = 0"
            )

    def close(self) -> None:
        with self._lock:
            self.conn.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


_db: Database | None = None
_db_lock = threading.Lock()


def get_db(path: str | None = None) -> Database:
    """Process-wide singleton (tests pass an explicit path to get a fresh one)."""
    global _db
    from backend.config import settings
    with _db_lock:
        if path is not None:
            return Database(path)
        if _db is None:
            _db = Database(settings.db_path)
        return _db
