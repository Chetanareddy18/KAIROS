"""File connector — CSV / TSV / JSON / Parquet / Excel, plain or gzip/zstd compressed.

Works on local paths and globs (`data/exports/*.csv.gz`) as well as cloud object
storage and HTTP (`s3://bucket/kpis/*.parquet`, `https://...`) through DuckDB's
httpfs extension. DuckDB streams the file, so files larger than RAM are fine,
and when `aggregate` is configured the GROUP BY runs inside DuckDB: a multi-GB
raw export is reduced to a few KB of KPIs without ever loading it into pandas.
"""
from __future__ import annotations

import glob
import logging
import os
from pathlib import Path

import duckdb
import pandas as pd

from backend.connectors.base import (
    BaseConnector, ConnectorError, freq_to_interval, parse_since, to_canonical,
)

logger = logging.getLogger("kairos.connector.file")

_EXCEL   = (".xlsx", ".xls")
_PARQUET = (".parquet", ".pq")
_JSON    = (".json", ".jsonl", ".ndjson", ".json.gz", ".jsonl.gz", ".ndjson.gz")
_SQL_AGG = {"sum": "sum", "mean": "avg", "avg": "avg", "min": "min", "max": "max",
            "count": "count", "median": "median", "first": "first", "last": "last"}


def _is_remote(path: str) -> bool:
    return path.startswith(("s3://", "gs://", "gcs://", "http://", "https://", "az://", "abfss://"))


def _q(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def resolve_paths(path: str) -> list[str]:
    if _is_remote(path):
        return [path]
    matches = sorted(glob.glob(path))
    if not matches:
        raise ConnectorError(f"No files match '{path}'")
    return matches


def _reader_sql(paths: list[str], cfg: dict) -> str:
    first = paths[0].lower()
    plist = "[" + ", ".join("'" + p.replace("'", "''") + "'" for p in paths) + "]"
    if first.endswith(_PARQUET):
        return f"read_parquet({plist}, union_by_name = true)"
    if first.endswith(_JSON):
        return f"read_json_auto({plist}, union_by_name = true)"
    opts = ["union_by_name = true", "sample_size = 20000"]
    if cfg.get("delimiter"):
        opts.append(f"delim = '{cfg['delimiter']}'")
    if first.endswith(".zst"):
        opts.append("compression = 'zstd'")
    return f"read_csv_auto({plist}, {', '.join(opts)})"


def _open_duck(cfg: dict) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("SET TimeZone = 'UTC'")
    if _is_remote(str(cfg.get("path", ""))):
        con.execute("INSTALL httpfs; LOAD httpfs;")
        for key, setting in (("s3_region", "s3_region"), ("s3_endpoint", "s3_endpoint")):
            if cfg.get(key):
                con.execute(f"SET {setting} = '{cfg[key]}'")
        if cfg.get("s3_access_key_id_env"):
            con.execute(f"SET s3_access_key_id = '{os.getenv(cfg['s3_access_key_id_env'], '')}'")
        if cfg.get("s3_secret_access_key_env"):
            con.execute(f"SET s3_secret_access_key = '{os.getenv(cfg['s3_secret_access_key_env'], '')}'")
    return con


def load_files(paths: list[str], cfg: dict, since: pd.Timestamp | None = None,
               limit: int | None = None) -> tuple[pd.DataFrame, bool]:
    """Read files into a DataFrame. Returns (frame, already_aggregated)."""
    if paths[0].lower().endswith(_EXCEL):
        frames = [pd.read_excel(p, sheet_name=cfg.get("sheet", 0)) for p in paths]
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        return (df.head(limit) if limit else df), False

    con    = _open_duck(cfg)
    src    = _reader_sql(paths, cfg)
    ts_col = cfg.get("ts_col", "timestamp")
    where, params = "", []
    if since is not None:
        # aggregated sources re-read the last (possibly partial) bucket so it is recomputed whole
        op = ">=" if cfg.get("aggregate") else ">"
        # rows DuckDB cannot parse are kept here; pandas parses and filters them precisely afterwards
        where = (f"WHERE TRY_CAST({_q(ts_col)} AS TIMESTAMPTZ) IS NULL "
                 f"OR TRY_CAST({_q(ts_col)} AS TIMESTAMPTZ) {op} ?")
        params.append(since.to_pydatetime())

    try:
        if cfg.get("aggregate") and limit is None:
            sql = _aggregate_sql(src, cfg, where)
            return con.execute(sql, params).df(), True
        sql = f"SELECT * FROM {src} {where}"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return con.execute(sql, params).df(), False
    except duckdb.Error as e:
        raise ConnectorError(f"Could not read {paths[0]}: {e}") from e
    finally:
        con.close()


def _aggregate_sql(src: str, cfg: dict, where: str) -> str:
    interval, _ = freq_to_interval(cfg["aggregate"].get("freq", "1h"))
    agg_cfg     = cfg["aggregate"].get("agg", "sum")
    ts          = f"time_bucket(INTERVAL '{interval}', TRY_CAST({_q(cfg.get('ts_col', 'timestamp'))} AS TIMESTAMPTZ))"

    def fn(col: str) -> str:
        name = agg_cfg.get(col, "sum") if isinstance(agg_cfg, dict) else agg_cfg
        if name not in _SQL_AGG:
            raise ConnectorError(f"Unsupported aggregate '{name}'")
        return _SQL_AGG[name]

    fmt = cfg.get("format", "wide")
    if fmt == "long" and not cfg.get("metric_name"):
        mcol, vcol = cfg.get("metric_col", "metric_name"), cfg.get("value_col", "value")
        f = fn(vcol) if isinstance(agg_cfg, dict) else fn("_")
        return (f"SELECT CAST({_q(mcol)} AS VARCHAR) AS metric_name, {ts} AS timestamp, "
                f"{f}(TRY_CAST({_q(vcol)} AS DOUBLE)) AS value "
                f"FROM {src} {where} GROUP BY 1, 2 ORDER BY 2")

    metrics = cfg.get("metrics") or {}
    if isinstance(metrics, list):
        metrics = {m: m for m in metrics}
    selects = [f"{ts} AS timestamp"]
    for col, name in metrics.items():
        selects.append(f"{fn(col)}(TRY_CAST({_q(col)} AS DOUBLE)) AS {_q(name)}")
    if cfg.get("count_metric"):
        selects.append(f"count(*) AS {_q(cfg['count_metric'])}")
    if len(selects) == 1:
        raise ConnectorError("aggregate needs 'metrics' (and/or 'count_metric')")
    return f"SELECT {', '.join(selects)} FROM {src} {where} GROUP BY 1 ORDER BY 1"


def post_aggregate_config(cfg: dict) -> dict:
    """Mapping to apply to a frame DuckDB already aggregated."""
    post = {k: v for k, v in cfg.items() if k not in ("aggregate", "count_metric", "metrics", "metric_col",
                                                       "value_col", "metric_name", "format")}
    post["ts_col"] = "timestamp"
    if cfg.get("format") == "long" and not cfg.get("metric_name"):
        post["format"] = "long"
    else:
        post["format"] = "wide"
    return post


class FileConnector(BaseConnector):
    type        = "file"
    label       = "File (CSV / Excel / Parquet / JSON, local or cloud)"
    description = "Reads files from disk, a glob pattern, S3/GCS or HTTPS. Aggregation runs inside DuckDB."
    CONFIG_FIELDS = [
        {"name": "path", "label": "Path / glob / URL", "type": "text", "required": True,
         "help": "e.g. data/exports/*.csv.gz or s3://bucket/kpis/*.parquet"},
        {"name": "sheet", "label": "Excel sheet", "type": "text", "required": False},
        {"name": "delimiter", "label": "CSV delimiter", "type": "text", "required": False},
    ]

    def __init__(self, source_name: str, config: dict | None = None, **legacy):
        # v1 signature: CSVConnector(source_name, file_path, metric_col=..., value_col=..., ts_col=...)
        config = dict(config or {})
        if "file_path" in legacy:
            config["path"] = legacy.pop("file_path")
        config.update({k: v for k, v in legacy.items() if v is not None})
        super().__init__(source_name, config)
        self._aggregated = False

    def fetch_raw(self, state: dict):
        path = self.config.get("path")
        if not path:
            raise ConnectorError("'path' is required")
        paths = resolve_paths(path)
        since = parse_since(state) if self.config.get("incremental", True) else None
        df, self._aggregated = load_files(paths, self.config, since=since)
        size = sum(os.path.getsize(p) for p in paths if not _is_remote(p) and Path(p).exists())
        return df, state, {"files": len(paths), "bytes": size}

    def preview(self, limit: int = 20) -> pd.DataFrame:
        paths = resolve_paths(self.config.get("path", ""))
        df, self._aggregated = load_files(paths, self.config, limit=limit)
        return df

    def canonicalise(self, raw: pd.DataFrame) -> pd.DataFrame:
        if self._aggregated:
            return to_canonical(raw, post_aggregate_config(self.config))
        return to_canonical(raw, self.config)
