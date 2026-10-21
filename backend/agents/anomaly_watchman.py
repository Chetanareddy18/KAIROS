"""Agent 2: Anomaly Watchman — seasonal robust z-score + Prophet ensemble.

Every detected anomaly is persisted (primary key source+metric+timestamp), so a
point is reported as *new* exactly once — the pipeline alerts on new anomalies
only, never on the same historical spike every 15 minutes.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime

import pandas as pd

from backend.config import settings
from backend.db import Database, get_db
from backend.models.anomaly import AnomalyDetectionPipeline, SEVERITY_ORDER

logger = logging.getLogger("kairos.agent2")

_MAX_POINTS = 5000    # detection window per series (most recent points)


@dataclass
class AnomalyResult:
    metric_name:     str
    source:          str
    timestamp:       datetime
    observed_value:  float
    expected_value:  float
    deviation_score: float     # signed, robust sigmas
    method:          str       # "robust_z" | "prophet" | "prophet+robust_z"
    severity:        str       # "low" | "medium" | "high" | "critical"
    is_new:          bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = pd.Timestamp(self.timestamp).isoformat()
        return d


class AnomalyWatchmanAgent:
    def __init__(self, db: Database | str | None = None, z_threshold: float | None = None,
                 use_prophet: bool | None = None):
        self.db = db if isinstance(db, Database) else get_db(db) if isinstance(db, str) else get_db()
        self.z_threshold = z_threshold if z_threshold is not None else settings.z_threshold
        self.detector = AnomalyDetectionPipeline(
            z_threshold=self.z_threshold,
            use_prophet=settings.use_prophet if use_prophet is None else use_prophet,
        )

    def detect(self, persist: bool = True) -> list[AnomalyResult]:
        """Scan every series; returns all anomalies found, with `is_new` marking first sightings."""
        pairs = self.db.execute("SELECT DISTINCT source, metric_name FROM metrics")
        series = {}
        for source, metric in pairs:
            df = self.db.df(
                "SELECT timestamp, value FROM metrics WHERE source = ? AND metric_name = ? "
                "ORDER BY timestamp DESC LIMIT ?",
                [source, metric, _MAX_POINTS],
            )
            if len(df) >= 10:
                series[(source, metric)] = df.sort_values("timestamp")

        def analyse(item):
            (source, metric), df = item
            s = pd.Series(df["value"].to_numpy(), index=pd.DatetimeIndex(df["timestamp"]))
            return [
                AnomalyResult(
                    metric_name=metric, source=source, timestamp=p.timestamp,
                    observed_value=p.value, expected_value=p.expected,
                    deviation_score=round(p.score, 3), method=p.method, severity=p.severity,
                )
                for p in self.detector.detect(s)
            ]

        anomalies: list[AnomalyResult] = []
        # Prophet releases the GIL while sampling, so a small pool helps on many series
        with ThreadPoolExecutor(max_workers=4) as pool:
            for found in pool.map(analyse, series.items()):
                anomalies.extend(found)

        if persist and anomalies:
            self._persist(anomalies)
        logger.info("Watchman: %d anomalies (%d new) across %d series",
                    len(anomalies), sum(a.is_new for a in anomalies), len(series))
        return anomalies

    def _persist(self, anomalies: list[AnomalyResult]) -> None:
        frame = pd.DataFrame([{
            "source": a.source, "metric_name": a.metric_name, "timestamp": pd.Timestamp(a.timestamp),
            "observed_value": a.observed_value, "expected_value": a.expected_value,
            "deviation_score": a.deviation_score, "severity": a.severity, "method": a.method,
        } for a in anomalies])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        with self.db.locked() as conn:
            existing = conn.execute("SELECT source, metric_name, timestamp FROM anomalies").df()
            keys = set()
            if not existing.empty:
                existing["timestamp"] = pd.to_datetime(existing["timestamp"], utc=True)
                keys = set(zip(existing["source"], existing["metric_name"], existing["timestamp"]))
            for a, ts in zip(anomalies, frame["timestamp"]):
                a.is_new = (a.source, a.metric_name, ts) not in keys
            conn.register("_kairos_anom", frame)
            try:
                conn.execute(
                    "INSERT INTO anomalies (source, metric_name, timestamp, observed_value, expected_value, "
                    "deviation_score, severity, method) "
                    "SELECT source, metric_name, timestamp, observed_value, expected_value, deviation_score, "
                    "severity, method FROM _kairos_anom "
                    "ON CONFLICT (source, metric_name, timestamp) DO UPDATE SET "
                    "observed_value = excluded.observed_value, expected_value = excluded.expected_value, "
                    "deviation_score = excluded.deviation_score, severity = excluded.severity, "
                    "method = excluded.method"
                )
            finally:
                conn.unregister("_kairos_anom")

    # ── reads (dashboard) ────────────────────────────────────────────────────

    def list_anomalies(self, severity: str | None = None, source: str | None = None,
                       metric: str | None = None, limit: int = 500) -> list[dict]:
        clauses, params = [], []
        if severity and severity != "all":
            clauses.append("severity = ?")
            params.append(severity)
        if source:
            clauses.append("source = ?")
            params.append(source)
        if metric:
            clauses.append("metric_name = ?")
            params.append(metric)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        df = self.db.df(
            f"SELECT id, source, metric_name, timestamp, observed_value, expected_value, deviation_score, "
            f"severity, method, detected_at, alerted FROM anomalies {where} "
            f"ORDER BY timestamp DESC, abs(deviation_score) DESC LIMIT ?",
            [*params, int(limit)],
        )
        for col in ("timestamp", "detected_at"):
            if not df.empty:
                df[col] = df[col].map(lambda t: pd.Timestamp(t).isoformat())
        return df.to_dict(orient="records")

    def severity_counts(self) -> dict:
        rows = dict(self.db.execute("SELECT severity, count(*) FROM anomalies GROUP BY severity"))
        return {s: int(rows.get(s, 0)) for s in SEVERITY_ORDER}

    def recent(self, hours: int = 24) -> list[AnomalyResult]:
        """Anomalies in the last `hours` before each series' newest point (investigation input)."""
        df = self.db.df(
            """
            SELECT a.* FROM anomalies a
            JOIN (SELECT source, metric_name, max(timestamp) AS last_ts FROM metrics GROUP BY 1, 2) m
              ON a.source = m.source AND a.metric_name = m.metric_name
            WHERE a.timestamp >= m.last_ts - to_hours(CAST(? AS BIGINT))
            ORDER BY a.timestamp
            """,
            [int(hours)],
        )
        return [
            AnomalyResult(
                metric_name=r.metric_name, source=r.source, timestamp=r.timestamp,
                observed_value=r.observed_value, expected_value=r.expected_value,
                deviation_score=r.deviation_score, method=r.method, severity=r.severity,
            )
            for r in df.itertuples()
        ]
