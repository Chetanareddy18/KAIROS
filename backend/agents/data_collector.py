"""Agent 1: Data Collector — pulls every registered source in parallel, incrementally,
normalises to (source, metric_name, value, timestamp) and upserts into DuckDB.

Sources live in the `sources` table. They come from `sources.yaml` (managed_by
= file), from the dashboard / API (managed_by = api), or are created
automatically when a push client or uploaded file first sends data.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from backend.config import settings
from backend.connectors.base import BaseConnector, ConnectorError, to_canonical
from backend.connectors.registry import build_connector
from backend.db import Database, get_db, utcnow

logger = logging.getLogger("kairos.agent1")

_SOURCE_COLS = ["name", "type", "config", "enabled", "managed_by", "description", "created_at",
                "last_sync", "last_status", "last_error", "last_rows", "last_bytes",
                "last_duration_ms", "total_rows"]
_SECRET_KEYS = ("password", "secret", "token", "api_key", "apikey")


def _mask(config: dict) -> dict:
    out = {}
    for k, v in config.items():
        if isinstance(v, dict):
            out[k] = _mask(v)
        elif any(s in k.lower() for s in _SECRET_KEYS) and not k.endswith("_env") and v:
            out[k] = "••••••"
        elif k == "url" and isinstance(v, str) and "@" in v and "://" in v:
            scheme, rest = v.split("://", 1)
            creds, host = rest.rsplit("@", 1)
            user = creds.split(":", 1)[0]
            out[k] = f"{scheme}://{user}:••••@{host}" if ":" in creds and "${" not in creds else v
        else:
            out[k] = v
    return out


class DataCollectorAgent:
    def __init__(self, db: Database | str | None = None):
        # accepts a Database, a path (v1 signature) or nothing (process singleton)
        self.db = db if isinstance(db, Database) else get_db(db) if isinstance(db, str) else get_db()
        self._adhoc: dict[str, BaseConnector] = {}

    # ── source registry ──────────────────────────────────────────────────────

    def register(self, connector: BaseConnector) -> None:
        """Register an in-memory connector object (programmatic use, tests)."""
        self._adhoc[connector.source_name] = connector
        self.upsert_source(connector.source_name, connector.type, connector.raw_config,
                           managed_by="code", description=connector.label)

    def upsert_source(self, name: str, type_: str, config: dict, enabled: bool = True,
                      description: str = "", managed_by: str = "api") -> dict:
        build_connector(name, type_, config)   # validates the type early
        self.db.execute(
            "INSERT INTO sources (name, type, config, enabled, managed_by, description) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET "
            "type = excluded.type, config = excluded.config, enabled = excluded.enabled, "
            "managed_by = excluded.managed_by, description = excluded.description",
            [name, type_, json.dumps(config, default=str), enabled, managed_by, description],
        )
        return self.get_source(name)

    def delete_source(self, name: str, purge_data: bool = False) -> None:
        self.db.execute("DELETE FROM sources WHERE name = ?", [name])
        self.db.clear_state(name)
        self._adhoc.pop(name, None)
        if purge_data:
            self.db.execute("DELETE FROM metrics WHERE source = ?", [name])
            self.db.execute("DELETE FROM anomalies WHERE source = ?", [name])

    def list_sources(self, mask: bool = True) -> list[dict]:
        rows = self.db.execute(f"SELECT {', '.join(_SOURCE_COLS)} FROM sources ORDER BY name")
        return [self._row(r, mask) for r in rows]

    def get_source(self, name: str, mask: bool = True) -> dict | None:
        rows = self.db.execute(f"SELECT {', '.join(_SOURCE_COLS)} FROM sources WHERE name = ?", [name])
        return self._row(rows[0], mask) if rows else None

    def _row(self, r, mask: bool) -> dict:
        d = dict(zip(_SOURCE_COLS, r))
        d["config"] = json.loads(d["config"]) if d["config"] else {}
        if mask:
            d["config"] = _mask(d["config"])
        for k in ("created_at", "last_sync"):
            d[k] = d[k].isoformat() if d[k] is not None else None
        d["state"] = self.db.get_state(d["name"])
        if "files" in d["state"]:
            d["state"] = {**d["state"], "files": len(d["state"]["files"])}
        return d

    def load_sources_file(self, path: str | None = None) -> int:
        path = path or settings.sources_file
        p = Path(path)
        if not p.exists():
            return 0
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        count = 0
        for entry in data.get("sources", []):
            try:
                name, type_ = entry["name"], entry["type"]
                cfg = {k: v for k, v in entry.items() if k not in ("name", "type", "enabled", "description")}
                self.upsert_source(name, type_, cfg, enabled=entry.get("enabled", True),
                                   description=entry.get("description", ""), managed_by="file")
                count += 1
            except Exception as e:  # noqa: BLE001
                logger.error("Bad source entry in %s: %s (%s)", path, entry, e)
        logger.info("Loaded %d source(s) from %s", count, path)
        return count

    def connector_for(self, name: str) -> BaseConnector:
        if name in self._adhoc:
            return self._adhoc[name]
        src = self.get_source(name, mask=False)
        if src is None:
            raise ConnectorError(f"Unknown source '{name}'")
        return build_connector(name, src["type"], src["config"])

    # ── collection ───────────────────────────────────────────────────────────

    def sync_source(self, name: str, full_refresh: bool = False) -> dict:
        t0 = time.perf_counter()
        try:
            connector = self.connector_for(name)
            state = {} if full_refresh else self.db.get_state(name)
            result = connector.fetch(state)
            df = self._normalise(result.df, name)
            stored = self.db.upsert_metrics(df)
            new_state = dict(result.state)
            if not df.empty:
                new_state["since"] = df["timestamp"].max().isoformat()
            elif "since" in state:
                new_state["since"] = state["since"]
            self.db.set_state(name, new_state)
            ms = int((time.perf_counter() - t0) * 1000)
            self._record(name, "ok", None, stored, int(result.stats.get("bytes", 0)), ms)
            logger.info("Source '%s': %d rows (%s) in %d ms", name, stored, result.stats, ms)
            return {"source": name, "status": "ok", "rows": stored, "duration_ms": ms,
                    "metrics": sorted(df["metric_name"].unique().tolist()) if not df.empty else [],
                    **{k: v for k, v in result.stats.items() if k != "file_names" or v}}
        except Exception as e:  # noqa: BLE001 — one bad source must not stop the others
            ms = int((time.perf_counter() - t0) * 1000)
            self._record(name, "error", str(e)[:500], 0, 0, ms)
            logger.error("Source '%s' failed: %s", name, e)
            return {"source": name, "status": "error", "error": str(e), "rows": 0, "duration_ms": ms}

    def collect_all(self) -> dict:
        names = [s["name"] for s in self.list_sources(mask=False)
                 if s["enabled"] and s["type"] not in ("push", "webhook", "edge")]
        if not names:
            return {"collected": 0, "errors": [], "sources": []}
        results = []
        with ThreadPoolExecutor(max_workers=min(settings.connector_workers, len(names))) as pool:
            futures = {pool.submit(self.sync_source, n): n for n in names}
            for fut, name in futures.items():
                try:
                    results.append(fut.result(timeout=settings.connector_timeout_s))
                except FutureTimeout:
                    self._record(name, "error", "timeout", 0, 0, settings.connector_timeout_s * 1000)
                    results.append({"source": name, "status": "error", "error": "timeout", "rows": 0})
        errors = [{"source": r["source"], "error": r.get("error")} for r in results if r["status"] != "ok"]
        return {"collected": sum(r["rows"] for r in results), "errors": errors, "sources": results}

    def ingest_dataframe(self, source: str, df: pd.DataFrame, mapping: dict | None = None,
                         bytes_received: int = 0, auto_create: bool = True,
                         source_type: str = "push") -> dict:
        """Store data that was pushed to KAIROS (webhook, edge agent, upload, fast transfer)."""
        t0 = time.perf_counter()
        if self.get_source(source) is None:
            if not auto_create:
                raise ConnectorError(f"Unknown source '{source}'")
            self.upsert_source(source, source_type, {"mapping": mapping or {}}, description="created on first push",
                               managed_by="push")
        canonical = df if set(["metric_name", "value", "timestamp"]).issubset(df.columns) and not mapping \
            else to_canonical(df, mapping or {})
        norm = self._normalise(canonical, source)
        stored = self.db.upsert_metrics(norm)
        ms = int((time.perf_counter() - t0) * 1000)
        self._record(source, "ok", None, stored, bytes_received, ms)
        return {"source": source, "rows": stored, "duration_ms": ms,
                "metrics": sorted(norm["metric_name"].unique().tolist()) if not norm.empty else []}

    def _record(self, name, status, error, rows, nbytes, ms) -> None:
        self.db.execute(
            "UPDATE sources SET last_sync = now(), last_status = ?, last_error = ?, last_rows = ?, "
            "last_bytes = ?, last_duration_ms = ?, total_rows = total_rows + ? WHERE name = ?",
            [status, error, rows, nbytes, ms, rows, name],
        )

    @staticmethod
    def _normalise(df: pd.DataFrame, source: str) -> pd.DataFrame:
        required = {"metric_name", "value", "timestamp"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"'{source}' missing columns: {missing}")
        out = pd.DataFrame({
            "source":      source,
            "metric_name": df["metric_name"].astype(str).str.strip(),
            "value":       pd.to_numeric(df["value"], errors="coerce"),
            "timestamp":   pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="mixed"),
        })
        out = out[np.isfinite(out["value"].astype(float))] if not out.empty else out
        return out.dropna(subset=["value", "timestamp"]).reset_index(drop=True)

    # v1 name kept for callers that stored frames directly
    def _store(self, df: pd.DataFrame) -> None:
        self.db.upsert_metrics(df)

    # ── reads ────────────────────────────────────────────────────────────────

    def get_series(self, metric_name: str, hours: int = 168, source: str | None = None) -> pd.DataFrame:
        """Last `hours` of a metric, measured back from its newest point (works for historical datasets)."""
        params: list = [metric_name]
        src_clause = ""
        if source:
            src_clause = " AND source = ?"
            params.append(source)
        df = self.db.df(
            f"""
            WITH m AS (SELECT * FROM metrics WHERE metric_name = ?{src_clause})
            SELECT source, metric_name, timestamp, value FROM m
            WHERE timestamp >= (SELECT max(timestamp) FROM m) - to_hours(CAST(? AS BIGINT))
            ORDER BY timestamp
            """,
            [*params, int(hours)],
        )
        return df

    def list_metrics(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT metric_name, source, count(*), min(timestamp), max(timestamp), arg_max(value, timestamp) "
            "FROM metrics GROUP BY metric_name, source ORDER BY source, metric_name"
        )
        return [
            {"metric_name": r[0], "source": r[1], "points": r[2],
             "first": r[3].isoformat() if r[3] else None, "last": r[4].isoformat() if r[4] else None,
             "latest_value": r[5]}
            for r in rows
        ]

    def get_all_metric_names(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT DISTINCT metric_name FROM metrics")]

    def overview(self) -> dict:
        r = self.db.execute(
            "SELECT count(*), count(DISTINCT source), count(DISTINCT (source, metric_name)), max(ingested_at) "
            "FROM metrics"
        )[0]
        return {"points": r[0], "sources_with_data": r[1], "series": r[2],
                "last_ingest": r[3].isoformat() if r[3] else None,
                "sources_registered": self.db.scalar("SELECT count(*) FROM sources")}
