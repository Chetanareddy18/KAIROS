"""Storage, anomaly detection, DYNOTEARS recovery, root-cause ranking, LLM-Modulo verification."""
import duckdb
import numpy as np
import pandas as pd

from backend.agents.anomaly_watchman import AnomalyWatchmanAgent
from backend.agents.causal_investigator import CausalInvestigatorAgent
from backend.agents.data_collector import DataCollectorAgent
from backend.agents.nl_reporter import NLReporterAgent
from backend.db import Database
from backend.demo.synthetic import TRUE_EDGES, generate
from backend.models.anomaly import AnomalyDetectionPipeline, severity_for
from backend.models.dynotears import dynotears
from backend.models.slac import SemanticLayerAutoConstructor


def _seed(db):
    c = DataCollectorAgent(db)
    df = generate(seed=42)
    for source, part in df.groupby("source"):
        c.ingest_dataframe(source, part[["metric_name", "value", "timestamp"]])
    return c


# ── storage ──────────────────────────────────────────────────────────────────

def test_upsert_is_idempotent(db):
    df = pd.DataFrame({"source": "s", "metric_name": "m", "value": [1.0, 2.0],
                       "timestamp": pd.to_datetime(["2026-01-01", "2026-01-02"], utc=True)})
    db.upsert_metrics(df)
    db.upsert_metrics(df)
    db.upsert_metrics(df.assign(value=[5.0, 6.0]))           # corrections overwrite
    assert db.scalar("SELECT count(*) FROM metrics") == 2
    assert db.scalar("SELECT sum(value) FROM metrics") == 11.0


def test_legacy_table_is_migrated(tmp_path):
    path = str(tmp_path / "legacy.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE metrics (id VARCHAR, source VARCHAR, metric_name VARCHAR, value DOUBLE, "
                "timestamp TIMESTAMPTZ, ingested_at TIMESTAMPTZ)")
    con.execute("INSERT INTO metrics VALUES ('1','s','m',1,'2026-01-01',now()), ('2','s','m',1,'2026-01-01',now())")
    con.close()
    db = Database(path)
    assert db.scalar("SELECT count(*) FROM metrics") == 1     # duplicate removed, PK added
    db.close()


# ── detection ────────────────────────────────────────────────────────────────

def test_detector_finds_injected_spike_and_ignores_noise():
    rng = np.random.default_rng(0)
    idx = pd.date_range("2026-01-01", periods=300, freq="h", tz="UTC")
    s = pd.Series(100 + rng.normal(0, 2, 300), index=idx)
    s.iloc[150] = 140                                          # 20 sigma
    found = AnomalyDetectionPipeline(z_threshold=3.5, use_prophet=False).detect(s)
    assert [p.timestamp for p in found] == [idx[150]]
    assert found[0].severity == "critical"


def test_severity_bands():
    assert [severity_for(x) for x in (3.6, 5, 7, -12)] == ["low", "medium", "high", "critical"]


def test_watchman_reports_each_anomaly_once(db):
    _seed(db)
    w = AnomalyWatchmanAgent(db, use_prophet=False)
    first = w.detect()
    assert first and all(a.is_new for a in first)
    counts = w.severity_counts()
    assert all(counts[s] > 0 for s in ("low", "medium", "high", "critical"))
    second = w.detect()
    assert not any(a.is_new for a in second)                   # no repeat alerts


# ── causal discovery ─────────────────────────────────────────────────────────

def test_dynotears_recovers_lagged_chain():
    rng = np.random.default_rng(1)
    T, X = 600, np.zeros((600, 3))
    for t in range(1, T):                                      # x0 -> x1 -> x2, lag 1
        X[t, 0] = 0.3 * X[t - 1, 0] + rng.normal()
        X[t, 1] = 0.8 * X[t - 1, 0] + rng.normal()
        X[t, 2] = 0.8 * X[t - 1, 1] + rng.normal()
    X = (X - X.mean(0)) / X.std(0)
    res = dynotears(X, p=1)
    A = np.abs(res.A)
    assert A[0, 1] > 0.3 and A[1, 2] > 0.3
    assert A[1, 0] < 0.15 and A[2, 1] < 0.15 and A[2, 0] < 0.15   # no reversed edges
    assert res.h < 1e-6                                            # acyclic


def test_investigator_recovers_ground_truth_and_origins(db):
    _seed(db)
    w = AnomalyWatchmanAgent(db, use_prophet=False)
    w.detect()
    report = CausalInvestigatorAgent(db, bootstrap=0).investigate(w.recent(24))
    assert report.method == "dynotears"
    found = {(e["from"], e["to"]) for e in report.cbmg.to_dict()["edges"]}
    truth = {(c, e) for c, e, _w, _l in TRUE_EDGES}
    recall = len(found & truth) / len(truth)
    precision = len(found & truth) / max(1, len(found))
    assert recall >= 0.8 and precision >= 0.8, (recall, precision, found - truth)
    assert {"ad_spend_usd", "delivery_delay_hrs"} <= set(report.origins)
    top_paths = [rc.path for rc in report.root_causes[:6]]
    assert any(p[0] == "ad_spend_usd" and p[-1] in ("daily_revenue", "order_count") for p in top_paths)


# ── semantic layer ───────────────────────────────────────────────────────────

def test_slac_infers_long_wide_and_raw():
    long = pd.DataFrame({"metric": ["a", "b"] * 5, "value": range(10),
                         "timestamp": pd.date_range("2026-01-01", periods=10, freq="h").astype(str)})
    assert SemanticLayerAutoConstructor().suggest_mapping(long)["mapping"]["format"] == "long"
    raw = pd.DataFrame({"created_at": ["2026-01-01 10:03", "2026-01-01 10:07", "2026-01-01 12:55",
                                       "2026-01-01 12:56", "2026-01-02 01:00"],
                        "amount": [5, 6, 7, 8, 9], "region": ["n", "s", "n", "s", "e"]})
    m = SemanticLayerAutoConstructor().suggest_mapping(raw)["mapping"]
    assert m["ts_col"] == "created_at" and m["metrics"] == ["amount"] and "aggregate" in m
    sem = SemanticLayerAutoConstructor().build(["customer_churn_rate", "daily_revenue"], use_llm=False)
    by = {x["column"]: x for x in sem["metrics"]}
    assert by["customer_churn_rate"]["higher_is_better"] is False
    assert by["daily_revenue"]["category"] == "revenue"


# ── LLM-Modulo ───────────────────────────────────────────────────────────────

def test_llm_modulo_rejects_hallucinations(db):
    _seed(db)
    w = AnomalyWatchmanAgent(db, use_prophet=False)
    w.detect()
    recent = w.recent(24)
    rep = NLReporterAgent()
    top = rep._top_anomalies(recent)
    allowed = rep._allowed_numbers(top, [], len(recent))
    known = {a.metric_name for a in recent}
    a = top[0]
    good = f"{a.metric_name} moved to {a.observed_value:,.2f} versus {a.expected_value:,.2f}."
    assert rep.verify(good, allowed, known) == []
    bad = f"{a.metric_name} moved to 987654.32 and marketing_budget_index collapsed."
    issues = rep.verify(bad, allowed, known)
    assert any("987654.32" in i for i in issues) and any("marketing_budget_index" in i for i in issues)


def test_template_report_is_grounded(db):
    _seed(db)
    w = AnomalyWatchmanAgent(db, use_prophet=False)
    w.detect()
    recent = w.recent(24)
    inv = CausalInvestigatorAgent(db, bootstrap=0).investigate(recent)
    result = NLReporterAgent().generate_report(recent, inv.root_causes, inv.origins)
    assert result.verified and result.engine == "template"
    rep = NLReporterAgent()
    known = {a.metric_name for a in recent} | {m for rc in inv.root_causes for m in rc.path}
    allowed = rep._allowed_numbers(rep._top_anomalies(recent), inv.root_causes, len(recent))
    assert rep.verify(result.text, allowed, known) == []
