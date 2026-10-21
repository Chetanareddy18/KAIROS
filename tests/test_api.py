"""API end-to-end: seed -> pipeline -> anomalies -> causal -> report, sources, push, upload, fast transfer."""
import gzip
import hashlib
import io

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.demo.synthetic import generate_transactions


@pytest.fixture(scope="module")
def client():
    from backend.main import app
    with TestClient(app) as c:
        yield c


def test_health_and_status(client):
    assert client.get("/health").json()["status"] == "ok"
    s = client.get("/api/v1/status").json()
    assert s["agents"] == 5 and "capabilities" in s


def test_seed_pipeline_and_analysis(client):
    seeded = client.post("/api/v1/dev/seed").json()
    assert seeded["total_metrics"] == 15 and len(seeded["sources"]) == 4

    run = client.post("/api/v1/pipeline/run").json()
    assert run["new_anomalies"] > 0 and run["alertable"] > 0
    assert run["report_meta"]["verified"] is True
    assert {"ad_spend_usd", "delivery_delay_hrs"} <= set(run["origins"])

    rerun = client.post("/api/v1/pipeline/run").json()
    assert rerun["new_anomalies"] == 0 and rerun["alertable"] == 0      # no duplicate alerts

    an = client.get("/api/v1/anomalies", params={"severity": "critical"}).json()
    assert an["count"] > 0 and all(a["severity"] == "critical" for a in an["anomalies"])

    series = client.get("/api/v1/metrics/ad_spend_usd/series", params={"hours": 72}).json()
    assert series["points"] and any(p["anomaly"] for p in series["points"])

    inv = client.get("/api/v1/investigation/latest").json()
    assert inv["cbmg"]["edges"] and inv["root_causes"]

    rep = client.post("/api/v1/report").json()
    assert rep["verified"] and "ad_spend_usd" in rep["report"]

    assert client.get("/api/v1/alerts/history").json()["history"]
    assert len(client.get("/api/v1/pipeline/runs").json()["runs"]) >= 2


def test_push_ingest(client):
    records = [{"metric_name": "edge_metric", "value": i, "timestamp": f"2026-02-01T{i:02d}:00:00Z"}
               for i in range(12)]
    r = client.post("/api/v1/ingest", json={"source": "edge_store_1", "records": records}).json()
    assert r["rows"] == 12
    assert client.get("/api/v1/sources/edge_store_1").json()["type"] == "push"


def test_sources_crud_test_and_sync(client, tmp_path):
    path = tmp_path / "kpis.csv"
    pd.DataFrame({"day": pd.date_range("2026-03-01", periods=30, freq="D").astype(str),
                  "visits": range(30), "signups": range(30)}).to_csv(path, index=False)
    probe = client.post("/api/v1/sources/test", json={"type": "file", "config": {"path": str(path)}}).json()
    assert probe["ok"] and probe["slac"]["mapping"]["ts_col"] == "day"

    body = {"name": "web_kpis", "type": "file", "config": {"path": str(path), **probe["slac"]["mapping"]}}
    assert client.post("/api/v1/sources", json=body).status_code == 201
    assert client.post("/api/v1/sources", json=body).status_code == 409
    sync = client.post("/api/v1/sources/web_kpis/sync").json()
    assert sync["status"] == "ok" and sync["rows"] == 60
    assert client.post("/api/v1/sources/web_kpis/sync").json()["rows"] == 0
    assert any(s["name"] == "web_kpis" for s in client.get("/api/v1/sources").json()["sources"])
    assert client.delete("/api/v1/sources/web_kpis", params={"purge": True}).status_code == 200
    assert client.get("/api/v1/sources/web_kpis").status_code == 404


def test_upload_with_slac_mapping(client):
    tx = generate_transactions(20_000, days=5)
    buf = io.BytesIO(tx.to_csv(index=False).encode())
    up = client.post("/api/v1/files", files={"file": ("orders.csv", buf, "text/csv")}).json()
    assert up["suggestion"]["mapping"]["ts_col"] == "created_at"
    res = client.post(f"/api/v1/files/{up['file_id']}/ingest", json={
        "source": "uploaded_erp",
        "mapping": {"ts_col": "created_at", "metrics": {"amount": "revenue"},
                    "aggregate": {"freq": "1h", "agg": "sum"}, "count_metric": "orders"},
    }).json()
    assert res["aggregated_at_source"] and res["kpi_rows"] < 20_000
    assert set(res["metrics"]) == {"revenue", "orders"}


def test_fast_transfer_roundtrip_with_ingest(client):
    tx = generate_transactions(30_000, days=3)
    data = tx.to_csv(index=False).encode()
    chunk = 256 * 1024
    st = client.post("/api/v1/transfer/start", json={
        "filename": "big_orders.csv", "size_bytes": len(data), "chunk_size": chunk,
        "sha256": hashlib.sha256(data).hexdigest(), "compression": "gzip"}).json()
    parts = [data[i:i + chunk] for i in range(0, len(data), chunk)]
    for i in range(0, len(parts), 2):                            # upload half ...
        r = client.put(f"/api/v1/transfer/{st['id']}/chunk/{i}", content=gzip.compress(parts[i]),
                       headers={"X-Chunk-SHA256": hashlib.sha256(parts[i]).hexdigest()})
        assert r.status_code == 200
    status = client.get(f"/api/v1/transfer/{st['id']}").json()
    assert status["missing"] == list(range(1, len(parts), 2))    # ... resume knows what's left
    for i in status["missing"]:
        client.put(f"/api/v1/transfer/{st['id']}/chunk/{i}", content=gzip.compress(parts[i]))
    done = client.post(f"/api/v1/transfer/{st['id']}/complete", json={
        "ingest": True, "source": "ft_erp",
        "mapping": {"ts_col": "created_at", "metrics": {"amount": "revenue"},
                    "aggregate": {"freq": "1h", "agg": "sum"}, "count_metric": "orders"}}).json()
    assert done["status"] == "completed" and done["bytes_on_wire"] < len(data)
    assert done["ingest"]["rows"] > 0


def test_api_key_enforced(monkeypatch, client):
    from backend import config
    monkeypatch.setattr(config.settings.__class__, "api_key", property(lambda self: "s3cret"))
    assert client.get("/api/v1/status").status_code == 401
    assert client.get("/api/v1/status", headers={"X-API-Key": "s3cret"}).status_code == 200
    assert client.get("/health").status_code == 200
