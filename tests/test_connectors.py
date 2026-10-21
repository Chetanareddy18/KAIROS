"""Connectors: mapping, files (CSV/gz/Parquet/Excel), SQL push-down, REST paging, FTP new-file tracking."""
import json
import socket
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd
import pytest

from backend.agents.data_collector import DataCollectorAgent
from backend.connectors.base import ConnectorError, to_canonical
from backend.connectors.csv_connector import CSVConnector
from backend.connectors.file_connector import FileConnector
from backend.connectors.registry import build_connector, describe_types
from backend.connectors.rest_connector import RESTConnector
from backend.connectors.sftp_connector import SFTPConnector
from backend.connectors.sql_connector import SQLConnector
from backend.demo.synthetic import generate_transactions


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ── mapping ──────────────────────────────────────────────────────────────────

def test_long_format_mapping():
    raw = pd.DataFrame({"kpi": ["a", "b"], "val": ["1.5", "2"], "when": ["2026-01-01 10:00", "2026-01-01 11:00"]})
    out = to_canonical(raw, {"format": "long", "metric_col": "kpi", "value_col": "val", "ts_col": "when"})
    assert list(out.columns) == ["metric_name", "value", "timestamp"]
    assert out["value"].tolist() == [1.5, 2.0]
    assert str(out["timestamp"].dt.tz) == "UTC"


def test_wide_format_with_rename():
    raw = pd.DataFrame({"ts": ["2026-01-01", "2026-01-02"], "rev": [10, 20], "orders": [1, 2], "note": ["x", "y"]})
    out = to_canonical(raw, {"ts_col": "ts", "metrics": {"rev": "revenue"}})
    assert set(out["metric_name"]) == {"revenue"}
    out_all = to_canonical(raw, {"ts_col": "ts"})          # default: every numeric column
    assert set(out_all["metric_name"]) == {"rev", "orders"}


def test_raw_records_aggregated_to_kpis():
    tx = generate_transactions(5000, days=2)
    out = to_canonical(tx, {"ts_col": "created_at", "metrics": {"amount": "revenue"},
                            "aggregate": {"freq": "1h", "agg": "sum"}, "count_metric": "orders"})
    assert set(out["metric_name"]) == {"revenue", "orders"}
    assert out[out.metric_name == "orders"]["value"].sum() == 5000
    assert abs(out[out.metric_name == "revenue"]["value"].sum() - tx["amount"].sum()) < 0.01


def test_missing_timestamp_column_is_explained():
    with pytest.raises(ConnectorError, match="timestamp column"):
        to_canonical(pd.DataFrame({"x": [1]}), {"ts_col": "ts"})


# ── files ────────────────────────────────────────────────────────────────────

def test_file_connector_formats(tmp_path):
    df = pd.DataFrame({"metric_name": ["m"] * 3, "value": [1.0, 2.0, 3.0],
                       "timestamp": pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC")})
    df.to_csv(tmp_path / "a.csv", index=False)
    df.to_csv(tmp_path / "b.csv.gz", index=False, compression="gzip")
    df.to_parquet(tmp_path / "c.parquet")
    df.assign(timestamp=df["timestamp"].dt.tz_localize(None)).to_excel(tmp_path / "d.xlsx", index=False)
    for name in ("a.csv", "b.csv.gz", "c.parquet", "d.xlsx"):
        out = FileConnector("f", {"path": str(tmp_path / name)}).fetch({}).df
        assert len(out) == 3, name
        assert out["value"].sum() == 6.0, name


def test_file_glob_and_incremental(tmp_path):
    for day in (1, 2):
        pd.DataFrame({"metric_name": "m", "value": [day],
                      "timestamp": [f"2026-01-0{day} 00:00:00+00:00"]}).to_csv(tmp_path / f"exp_{day}.csv", index=False)
    conn = FileConnector("f", {"path": str(tmp_path / "exp_*.csv")})
    first = conn.fetch({})
    assert len(first.df) == 2
    since = {"since": first.df["timestamp"].max().isoformat()}
    assert conn.fetch(since).df.empty                       # nothing newer than the watermark


def test_file_pushdown_aggregation_large_raw(tmp_path):
    """A raw transaction export is reduced to hourly KPIs inside DuckDB."""
    tx = generate_transactions(200_000, days=7)
    path = tmp_path / "orders.csv.gz"
    tx.to_csv(path, index=False, compression="gzip")
    conn = FileConnector("erp", {"path": str(path), "ts_col": "created_at", "metrics": {"amount": "revenue"},
                                 "aggregate": {"freq": "1h", "agg": "sum"}, "count_metric": "orders"})
    res = conn.fetch({})
    orders = res.df[res.df.metric_name == "orders"]
    assert orders["value"].sum() == 200_000
    assert len(res.df) <= 2 * 7 * 24 + 2                    # KPI rows, not 200k raw rows


def test_legacy_csv_connector_signature(tmp_path):
    pd.DataFrame({"metric": ["x"], "v": [1], "t": ["2026-01-01"]}).to_csv(tmp_path / "x.csv", index=False)
    c = CSVConnector("legacy", file_path=str(tmp_path / "x.csv"), metric_col="metric", value_col="v", ts_col="t")
    assert c.fetch_df()["metric_name"].tolist() == ["x"]


# ── SQL ──────────────────────────────────────────────────────────────────────

def test_sql_connector_pushdown_and_since(tmp_path):
    db = tmp_path / "erp.sqlite"
    tx = generate_transactions(3000, days=3)
    with sqlite3.connect(db) as con:
        tx.to_sql("orders", con, index=False)
    query = ("SELECT strftime('%Y-%m-%d %H:00:00', created_at) AS timestamp, SUM(amount) AS revenue, "
             "COUNT(*) AS orders FROM orders WHERE created_at >= :since GROUP BY 1")
    conn = SQLConnector("erp", {"url": f"sqlite:///{db}", "query": query, "ts_col": "timestamp"})
    res = conn.fetch({})
    assert res.df[res.df.metric_name == "orders"]["value"].sum() == 3000
    last = res.df["timestamp"].max()
    again = conn.fetch({"since": last.isoformat()})
    assert again.df["timestamp"].min() >= last


# ── REST ─────────────────────────────────────────────────────────────────────

@pytest.fixture
def rest_server():
    pages = {1: [{"ts": "2026-01-01T00:00:00Z", "revenue": 10}, {"ts": "2026-01-01T01:00:00Z", "revenue": 11}],
             2: [{"ts": "2026-01-01T02:00:00Z", "revenue": 12}], 3: []}
    seen_headers = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            seen_headers["auth"] = self.headers.get("Authorization")
            page = int(q.get("page", ["1"])[0])
            body = json.dumps({"data": {"items": pages.get(page, [])}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    port = _free_port()
    srv = HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/orders", seen_headers
    srv.shutdown()


def test_rest_connector_paging_and_env_secret(rest_server, monkeypatch):
    url, seen = rest_server
    monkeypatch.setenv("SHOP_TOKEN", "abc123")
    conn = RESTConnector("shop", {"url": url, "records_path": "data.items", "ts_col": "ts",
                                  "headers": {"Authorization": "Bearer ${SHOP_TOKEN}"},
                                  "pagination": {"type": "page", "param": "page", "max_pages": 10}})
    res = conn.fetch({})
    assert res.df["value"].tolist() == [10, 11, 12]
    assert seen["auth"] == "Bearer abc123"


# ── FTP (real server via pyftpdlib) ──────────────────────────────────────────

@pytest.fixture
def ftp_server(tmp_path):
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer

    root = tmp_path / "ftp"
    (root / "exports").mkdir(parents=True)
    auth = DummyAuthorizer()
    auth.add_user("kairos", "secret", str(root), perm="elr")
    handler = type("H", (FTPHandler,), {"authorizer": auth})
    port = _free_port()
    srv = FTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=srv.serve_forever, kwargs={"timeout": 0.2}, daemon=True)
    t.start()
    time.sleep(0.2)
    yield port, root / "exports"
    srv.close_all()


def test_ftp_fetches_only_new_files(ftp_server, monkeypatch):
    port, folder = ftp_server
    monkeypatch.setenv("FTP_PASS", "secret")

    def drop(name, value):
        df = pd.DataFrame({"metric_name": ["sales"], "value": [value], "timestamp": [f"2026-01-0{value} 00:00"]})
        df.to_csv(folder / name, index=False, compression="gzip")

    drop("kpi_1.csv.gz", 1)
    drop("kpi_2.csv.gz", 2)
    conn = SFTPConnector("ftp", {"protocol": "ftp", "host": "127.0.0.1", "port": port, "username": "kairos",
                                 "password_env": "FTP_PASS", "folder": "/exports", "pattern": "kpi_*.csv.gz"})
    first = conn.fetch({})
    assert sorted(first.df["value"].tolist()) == [1, 2]
    assert first.stats["files"] == 2 and first.stats["bytes"] > 0
    second = conn.fetch(first.state)
    assert second.stats["files"] == 0 and second.df.empty        # nothing re-downloaded
    drop("kpi_3.csv.gz", 3)
    third = conn.fetch(second.state)
    assert third.df["value"].tolist() == [3]


def test_collector_end_to_end_with_state(db, tmp_path):
    path = tmp_path / "k.csv"
    pd.DataFrame({"metric_name": "m", "value": [1, 2],
                  "timestamp": ["2026-01-01 00:00Z", "2026-01-01 01:00Z"]}).to_csv(path, index=False)
    c = DataCollectorAgent(db)
    c.upsert_source("files", "file", {"path": str(path)})
    r1 = c.sync_source("files")
    assert r1["status"] == "ok" and r1["rows"] == 2
    r2 = c.sync_source("files")
    assert r2["rows"] == 0                                        # incremental: nothing new
    pd.DataFrame({"metric_name": "m", "value": [3], "timestamp": ["2026-01-01 02:00Z"]}).to_csv(
        path, mode="a", header=False, index=False)
    assert c.sync_source("files")["rows"] == 1
    assert db.scalar("SELECT count(*) FROM metrics") == 3
    src = c.get_source("files")
    assert src["last_status"] == "ok" and src["total_rows"] == 3


def test_bad_source_does_not_break_others(db, tmp_path):
    good = tmp_path / "g.csv"
    pd.DataFrame({"metric_name": "m", "value": [1], "timestamp": ["2026-01-01"]}).to_csv(good, index=False)
    c = DataCollectorAgent(db)
    c.upsert_source("good", "file", {"path": str(good)})
    c.upsert_source("broken", "file", {"path": str(tmp_path / "missing_*.csv")})
    res = c.collect_all()
    assert res["collected"] == 1
    assert [e["source"] for e in res["errors"]] == ["broken"]


def test_registry_and_secret_masking(db):
    assert {"sql", "file", "sftp", "rest", "sheets", "push"} <= {t["type"] for t in describe_types()}
    assert build_connector("x", "ftp", {"host": "h"}).config["protocol"] == "ftp"
    c = DataCollectorAgent(db)
    c.upsert_source("pg", "sql", {"url": "postgresql://bob:hunter2@db/erp", "query": "select 1", "password": "p"})
    shown = c.get_source("pg")["config"]
    assert "hunter2" not in shown["url"] and shown["password"] == "••••••"
    assert c.get_source("pg", mask=False)["config"]["password"] == "p"
