"""Connector framework.

Every source — SQL, files, SFTP/FTP, REST, Google Sheets, push — implements one
small contract:

    fetch(state) -> FetchResult(df, state, stats)

`df` is canonical (metric_name, value, timestamp); `state` is an opaque JSON dict
the collector persists between runs (watermark, processed files, cursors), so
each cycle only moves data that is new since the last one.

Mapping options shared by every connector (all optional):

    format:       long | wide              long = one row per (metric, ts); wide = one column per metric
    ts_col:       timestamp column          default "timestamp"
    metric_col:   metric-name column        long format, default "metric_name"
    value_col:    value column              long format, default "value"
    metric_name:  constant metric name      single-metric sources
    metrics:      [col, ...] | {col: name}  wide format; default = every numeric column
    aggregate:    {freq: "1h", agg: "sum" | {col: agg}}   turn raw records into KPIs at the source
    count_metric: name                      with aggregate: also emit row count per bucket
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger("kairos.connector")

CANONICAL = ["metric_name", "value", "timestamp"]
_ENV_RE   = re.compile(r"\$\{([A-Z0-9_]+)\}")
_FREQ_RE  = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")
_UNITS    = {
    "s": "second", "sec": "second", "second": "second", "seconds": "second",
    "m": "minute", "min": "minute", "minute": "minute", "minutes": "minute", "t": "minute",
    "h": "hour", "hr": "hour", "hour": "hour", "hours": "hour",
    "d": "day", "day": "day", "days": "day",
    "w": "week", "week": "week", "weeks": "week",
}


@dataclass
class FetchResult:
    df:    pd.DataFrame
    state: dict                     = field(default_factory=dict)
    stats: dict[str, Any]           = field(default_factory=dict)


class ConnectorError(RuntimeError):
    pass


# ── helpers ──────────────────────────────────────────────────────────────────

def expand_env(value: Any) -> Any:
    """Replace ${VAR} with environment values, recursively, so secrets never sit in config."""
    if isinstance(value, str):
        return _ENV_RE.sub(lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [expand_env(v) for v in value]
    return value


def secret(cfg: dict, key: str) -> str:
    """cfg[key] or the env var named by cfg[key + '_env']."""
    if cfg.get(key):
        return str(cfg[key])
    env_name = cfg.get(f"{key}_env")
    return os.getenv(env_name, "") if env_name else ""


def freq_to_interval(freq: str) -> tuple[str, str]:
    """'15min' -> ('15 minutes', '15min'): (DuckDB interval, pandas offset)."""
    m = _FREQ_RE.match(str(freq))
    if not m:
        raise ConnectorError(f"Bad aggregate freq '{freq}' (use e.g. 15min, 1h, 1d)")
    n, unit = int(m.group(1)), _UNITS.get(m.group(2).lower())
    if unit is None:
        raise ConnectorError(f"Bad aggregate unit in '{freq}'")
    pandas_unit = {"second": "s", "minute": "min", "hour": "h", "day": "D", "week": "W"}[unit]
    return f"{n} {unit}s", f"{n}{pandas_unit}"


def parse_since(state: dict) -> pd.Timestamp | None:
    since = state.get("since") if state else None
    return pd.Timestamp(since).tz_convert("UTC") if since else None


# ── canonicalisation ─────────────────────────────────────────────────────────

def to_canonical(raw: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Turn whatever the source returned into (metric_name, value, timestamp)."""
    if raw is None or raw.empty:
        return pd.DataFrame(columns=CANONICAL)
    df       = raw.copy()
    ts_col   = cfg.get("ts_col", "timestamp")
    fmt      = cfg.get("format") or _guess_format(df, cfg)

    if ts_col not in df.columns:
        raise ConnectorError(f"timestamp column '{ts_col}' not found (columns: {list(df.columns)[:20]})")
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True, errors="coerce", format="mixed")
    df = df.dropna(subset=[ts_col])

    if fmt == "long":
        metric_col = cfg.get("metric_col", "metric_name")
        value_col  = cfg.get("value_col", "value")
        if cfg.get("metric_name"):
            df["__metric"] = cfg["metric_name"]
            metric_col = "__metric"
        for col in (metric_col, value_col):
            if col not in df.columns:
                raise ConnectorError(f"column '{col}' not found (columns: {list(df.columns)[:20]})")
        out = pd.DataFrame({
            "metric_name": df[metric_col].astype(str),
            "value":       pd.to_numeric(df[value_col], errors="coerce"),
            "timestamp":   df[ts_col],
        })
        if cfg.get("aggregate"):
            out = _aggregate_long(out, cfg)
    else:
        metrics = cfg.get("metrics")
        if isinstance(metrics, dict):
            rename = {k: v for k, v in metrics.items() if k in df.columns}
        else:
            cols = metrics or [
                c for c in df.columns
                if c != ts_col and pd.api.types.is_numeric_dtype(df[c])
            ]
            rename = {c: c for c in cols if c in df.columns}
        if not rename and not cfg.get("count_metric"):
            raise ConnectorError("no metric columns found — set 'metrics' in the mapping")
        wide = df[[ts_col, *rename.keys()]].copy()
        for c in rename:
            wide[c] = pd.to_numeric(wide[c], errors="coerce")
        if cfg.get("aggregate"):
            wide = _aggregate_wide(wide, ts_col, rename, cfg)
            rename = {c: c for c in wide.columns if c != ts_col}
        else:
            wide = wide.rename(columns=rename)
            rename = {v: v for v in rename.values()}
        out = wide.melt(id_vars=[ts_col], value_vars=list(rename.keys()),
                        var_name="metric_name", value_name="value")
        out = out.rename(columns={ts_col: "timestamp"})

    out = out.dropna(subset=["value", "timestamp"])
    return out[CANONICAL].reset_index(drop=True)


def _guess_format(df: pd.DataFrame, cfg: dict) -> str:
    if cfg.get("metric_name"):
        return "long"
    if cfg.get("metric_col", "metric_name") in df.columns and cfg.get("value_col", "value") in df.columns:
        return "long"
    return "wide"


def _agg_for(cfg: dict, col: str) -> str:
    agg = cfg["aggregate"].get("agg", "sum")
    return agg.get(col, "sum") if isinstance(agg, dict) else agg


def _aggregate_long(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    _, offset = freq_to_interval(cfg["aggregate"].get("freq", "1h"))
    agg = cfg["aggregate"].get("agg", "sum")
    agg = agg if isinstance(agg, str) else "sum"
    df = df.copy()
    df["timestamp"] = df["timestamp"].dt.floor(offset)
    return df.groupby(["metric_name", "timestamp"], as_index=False)["value"].agg(agg)


def _aggregate_wide(df: pd.DataFrame, ts_col: str, rename: dict, cfg: dict) -> pd.DataFrame:
    _, offset = freq_to_interval(cfg["aggregate"].get("freq", "1h"))
    df = df.copy()
    df[ts_col] = df[ts_col].dt.floor(offset)
    grouped = df.groupby(ts_col)
    parts = {rename[c]: grouped[c].agg(_agg_for(cfg, c)) for c in rename}
    if cfg.get("count_metric"):
        parts[cfg["count_metric"]] = grouped.size()
    return pd.DataFrame(parts).reset_index()


def filter_since(df: pd.DataFrame, since: pd.Timestamp | None, inclusive: bool = False) -> pd.DataFrame:
    if since is None or df.empty:
        return df
    return df[df["timestamp"] >= since] if inclusive else df[df["timestamp"] > since]


# ── base class ───────────────────────────────────────────────────────────────

class BaseConnector:
    type: str = "base"
    label: str = "Base"
    description: str = ""
    # Field specs drive the "Add source" form in the dashboard.
    CONFIG_FIELDS: list[dict] = []
    # keep rows *at* the watermark: sources that aggregate in their own query re-send the last
    # (possibly partial) bucket, and the idempotent upsert simply refreshes it
    inclusive_since: bool = False

    def __init__(self, source_name: str, config: dict | None = None):
        self.source_name = source_name
        self.raw_config  = dict(config or {})
        self.config      = expand_env(self.raw_config)

    # subclasses implement this: return raw frame (any shape), new state, stats
    def fetch_raw(self, state: dict) -> tuple[pd.DataFrame, dict, dict]:
        raise NotImplementedError

    # subclasses may override when the raw frame is already canonical/aggregated
    def canonicalise(self, raw: pd.DataFrame) -> pd.DataFrame:
        return to_canonical(raw, self.config)

    def fetch(self, state: dict | None = None) -> FetchResult:
        state = dict(state or {})
        raw, new_state, stats = self.fetch_raw(state)
        df = self.canonicalise(raw)
        if self.config.get("incremental", True):
            # aggregated buckets: keep the last bucket so a partial one gets recomputed
            inclusive = self.inclusive_since or bool(self.config.get("aggregate"))
            df = filter_since(df, parse_since(state), inclusive=inclusive)
        stats = {"raw_rows": 0 if raw is None else len(raw), **stats}
        return FetchResult(df=df, state=new_state, stats=stats)

    def preview(self, limit: int = 20) -> pd.DataFrame:
        raw, _, _ = self.fetch_raw({})
        return raw.head(limit) if raw is not None else pd.DataFrame()

    def test_connection(self) -> dict:
        try:
            raw = self.preview(20)
            canonical = None
            try:
                canonical = self.canonicalise(raw)
            except ConnectorError as e:
                return {"ok": True, "message": f"Connected, but mapping needs attention: {e}",
                        "columns": list(map(str, raw.columns)), "sample": _records(raw),
                        "mapping_ok": False}
            return {
                "ok": True, "message": f"Connected — {len(raw)} sample rows",
                "columns": list(map(str, raw.columns)), "sample": _records(raw),
                "metrics": sorted(canonical["metric_name"].unique().tolist()) if canonical is not None else [],
                "mapping_ok": True,
            }
        except Exception as e:  # noqa: BLE001 — surface every failure to the UI
            return {"ok": False, "message": str(e), "columns": [], "sample": []}

    # legacy v1 API: connectors used to expose fetch() -> DataFrame directly
    def fetch_df(self) -> pd.DataFrame:
        return self.fetch({}).df


def _records(df: pd.DataFrame, limit: int = 10) -> list[dict]:
    if df is None or df.empty:
        return []
    head = df.head(limit).copy()
    for c in head.columns:
        if pd.api.types.is_datetime64_any_dtype(head[c]):
            head[c] = head[c].astype(str)
    return head.astype(object).where(head.notna(), None).to_dict(orient="records")
