"""Agent 1: Data Collector — ingests from all sources, normalises, stores in DuckDB."""
import logging

import duckdb
import pandas as pd

logger = logging.getLogger("kairos.agent1")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id          VARCHAR DEFAULT gen_random_uuid(),
    source      VARCHAR      NOT NULL,
    metric_name VARCHAR      NOT NULL,
    value       DOUBLE       NOT NULL,
    timestamp   TIMESTAMPTZ  NOT NULL,
    ingested_at TIMESTAMPTZ  DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_metrics_name_ts ON metrics (metric_name, timestamp);
"""


class DataCollectorAgent:
    def __init__(self, db_path: str = "kairos.duckdb"):
        self.conn       = duckdb.connect(db_path)
        self.connectors: list = []
        self.conn.executescript(_SCHEMA)

    def register(self, connector) -> None:
        self.connectors.append(connector)

    def collect_all(self) -> dict:
        total, errors = 0, []
        for c in self.connectors:
            name = getattr(c, "source_name", "unknown")
            try:
                df = self._normalise(c.fetch(), name)
                self._store(df)
                total += len(df)
                logger.info("Collected %d rows from '%s'", len(df), name)
            except Exception as e:
                logger.error("Connector '%s' failed: %s", name, e)
                errors.append({"source": name, "error": str(e)})
        return {"collected": total, "errors": errors}

    def _normalise(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        required = {"metric_name", "value", "timestamp"}
        missing  = required - set(df.columns)
        if missing:
            raise ValueError(f"'{source}' missing columns: {missing}")
        df = df.copy()
        df["source"]    = source
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["value"]     = pd.to_numeric(df["value"], errors="coerce")
        return df.dropna(subset=["value", "timestamp"])[
            ["source", "metric_name", "value", "timestamp"]
        ]

    def _store(self, df: pd.DataFrame) -> None:
        self.conn.execute(
            "INSERT INTO metrics (source, metric_name, value, timestamp) "
            "SELECT source, metric_name, value, timestamp FROM df"
        )

    def get_series(self, metric_name: str, hours: int = 168) -> pd.DataFrame:
        return self.conn.execute(
            "SELECT * FROM metrics "
            "WHERE metric_name = ? AND timestamp >= now() - INTERVAL (? || ' hours')::INTERVAL "
            "ORDER BY timestamp",
            [metric_name, str(hours)],
        ).df()

    def list_metrics(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT DISTINCT metric_name, source FROM metrics ORDER BY metric_name"
        ).fetchall()
        return [{"metric_name": r[0], "source": r[1]} for r in rows]

    def get_all_metric_names(self) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT DISTINCT metric_name FROM metrics"
            ).fetchall()
        ]
