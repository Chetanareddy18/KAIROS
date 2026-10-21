"""SQL connector — any SQLAlchemy database (PostgreSQL, MySQL, SQL Server, Oracle,
SQLite, Snowflake, BigQuery, Redshift, Databricks, ...).

The query runs *inside the source database*, so large tables are aggregated where
they live and only KPI rows cross the network ("push-down"). Use the `:since`
bind parameter for incremental loads — KAIROS fills it with the last timestamp it
stored for this source:

    SELECT date_trunc('hour', created_at) AS timestamp,
           SUM(total) AS revenue, COUNT(*) AS orders
    FROM orders WHERE created_at >= :since GROUP BY 1
"""
from __future__ import annotations

import logging
import threading

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from backend.connectors.base import BaseConnector, ConnectorError, parse_since

logger = logging.getLogger("kairos.connector.sql")

_EPOCH   = pd.Timestamp("1970-01-01", tz="UTC")
_engines: dict[str, Engine] = {}
_lock    = threading.Lock()


def _engine(url: str) -> Engine:
    with _lock:
        if url not in _engines:
            _engines[url] = create_engine(url, pool_pre_ping=True)
        return _engines[url]


class SQLConnector(BaseConnector):
    type        = "sql"
    label       = "SQL database"
    description = "Runs an (aggregating) query inside the source DB; only KPI rows travel."
    inclusive_since = True
    CONFIG_FIELDS = [
        {"name": "url", "label": "Connection URL", "type": "text", "required": True, "secret": True,
         "help": "postgresql://readonly:${DB_PASS}@host/db · sqlite:///data/erp.sqlite"},
        {"name": "query", "label": "Query", "type": "textarea", "required": True,
         "help": "Use :since for incremental loads, aggregate with GROUP BY at the source"},
    ]

    def __init__(self, source_name: str, config: dict | None = None, connection_url: str | None = None,
                 query: str | None = None, **legacy):
        # v1 signature: SQLConnector(source_name, connection_url, query, metric_col=..., ...)
        config = dict(config or {})
        if connection_url:
            config["url"] = connection_url
        if query:
            config["query"] = query
        config.update({k: v for k, v in legacy.items() if v is not None})
        super().__init__(source_name, config)

    def _run(self, since: pd.Timestamp | None, limit: int | None = None) -> pd.DataFrame:
        url, query = self.config.get("url"), self.config.get("query")
        if not url or not query:
            raise ConnectorError("'url' and 'query' are required")
        params = {}
        if ":since" in query:
            ts = since if since is not None else _EPOCH
            # SQLite compares ISO strings; drivers for real DBs accept datetimes
            params["since"] = ts.strftime("%Y-%m-%d %H:%M:%S") if url.startswith("sqlite") else ts.to_pydatetime()
        sql = f"SELECT * FROM ({query.rstrip().rstrip(';')}) AS kairos_q LIMIT {int(limit)}" if limit else query
        with _engine(url).connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def fetch_raw(self, state: dict):
        df = self._run(parse_since(state))
        return df, state, {"bytes": int(df.memory_usage(deep=True).sum()) if not df.empty else 0}

    def preview(self, limit: int = 20) -> pd.DataFrame:
        return self._run(None, limit=limit)
