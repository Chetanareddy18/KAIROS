"""Connector registry — maps a source `type` to its adapter class.

Adding support for a new kind of system means adding one small class here; the
agents downstream never know where data came from.
"""
from __future__ import annotations

import pandas as pd

from backend.connectors.base import BaseConnector, ConnectorError
from backend.connectors.csv_connector import CSVConnector
from backend.connectors.file_connector import FileConnector
from backend.connectors.rest_connector import RESTConnector
from backend.connectors.sftp_connector import SFTPConnector
from backend.connectors.sheets_connector import SheetsConnector
from backend.connectors.sql_connector import SQLConnector


class PushConnector(BaseConnector):
    """Sources that send data to KAIROS (webhooks, edge agent, fast transfer). Nothing to pull."""
    type        = "push"
    label       = "Push / Webhook / Edge agent"
    description = "The source POSTs to /api/v1/ingest (or uploads via Fast Transfer). No polling."
    CONFIG_FIELDS = []

    def fetch_raw(self, state: dict):
        return pd.DataFrame(), state, {"bytes": 0}

    def fetch(self, state=None):
        from backend.connectors.base import FetchResult
        return FetchResult(df=pd.DataFrame(columns=["metric_name", "value", "timestamp"]),
                           state=dict(state or {}), stats={"bytes": 0, "skipped": "push source"})

    def test_connection(self) -> dict:
        return {"ok": True, "message": "Push source — waiting for data on /api/v1/ingest",
                "columns": [], "sample": [], "mapping_ok": True}


CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {
    c.type: c for c in (SQLConnector, FileConnector, CSVConnector, SFTPConnector,
                        RESTConnector, SheetsConnector, PushConnector)
}
# common aliases people write in sources.yaml
CONNECTOR_TYPES.update({"ftp": SFTPConnector, "ftps": SFTPConnector, "excel": FileConnector,
                        "parquet": FileConnector, "s3": FileConnector, "http": RESTConnector,
                        "webhook": PushConnector, "edge": PushConnector})


def build_connector(name: str, type_: str, config: dict | None = None) -> BaseConnector:
    cls = CONNECTOR_TYPES.get(type_.lower())
    if cls is None:
        raise ConnectorError(f"Unknown connector type '{type_}'. Known: {sorted(CONNECTOR_TYPES)}")
    config = dict(config or {})
    if type_.lower() in ("ftp", "ftps"):
        config.setdefault("protocol", type_.lower())
    return cls(name, config)


def describe_types() -> list[dict]:
    """Field specs used by the dashboard to render the 'Add source' form."""
    mapping_fields = [
        {"name": "format", "label": "Data shape", "type": "select", "options": ["", "long", "wide"],
         "help": "long = metric_name/value/timestamp rows · wide = one column per metric"},
        {"name": "ts_col", "label": "Timestamp column", "type": "text", "default": "timestamp"},
        {"name": "metric_col", "label": "Metric-name column (long)", "type": "text"},
        {"name": "value_col", "label": "Value column (long)", "type": "text"},
        {"name": "metrics", "label": "Metric columns (wide, JSON list or {col: name})", "type": "json"},
        {"name": "aggregate", "label": "Aggregate raw rows (JSON)", "type": "json",
         "help": '{"freq": "1h", "agg": "sum"} — reduce raw records to KPIs at the source'},
        {"name": "count_metric", "label": "Row-count metric name", "type": "text"},
    ]
    seen, out = set(), []
    for cls in (SQLConnector, FileConnector, SFTPConnector, RESTConnector, SheetsConnector, PushConnector):
        if cls.type in seen:
            continue
        seen.add(cls.type)
        out.append({
            "type": cls.type, "label": cls.label, "description": cls.description,
            "fields": cls.CONFIG_FIELDS,
            "mapping_fields": [] if cls is PushConnector else mapping_fields,
        })
    return out
