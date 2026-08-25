"""KAIROS — all FastAPI routes."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger("kairos.api")
router = APIRouter()


def _pipeline(request: Request):
    p = getattr(request.app.state, "pipeline", None)
    if p is None:
        raise HTTPException(503, "Pipeline not initialised")
    return p


# ── Meta ──────────────────────────────────────────────────────────────────────

@router.get("/status")
def status():
    return {"status": "running", "version": "1.0.0", "agents": 5}


# ── Metrics ───────────────────────────────────────────────────────────────────

@router.get("/metrics")
def list_metrics(p=Depends(_pipeline)):
    return {"metrics": p.collector.list_metrics()}


@router.get("/metrics/{metric_name}/series")
def get_series(metric_name: str, hours: int = 168, p=Depends(_pipeline)):
    df = p.collector.get_series(metric_name, hours)
    return {"metric": metric_name, "points": df.to_dict(orient="records")}


# ── Collect ───────────────────────────────────────────────────────────────────

@router.post("/collect")
def trigger_collect(p=Depends(_pipeline)):
    return p.collector.collect_all()


# ── Anomalies ─────────────────────────────────────────────────────────────────

@router.get("/anomalies")
def get_anomalies(p=Depends(_pipeline)):
    anomalies = p.watchman.detect()
    return {
        "count": len(anomalies),
        "anomalies": [
            {
                "metric_name":     a.metric_name,
                "source":          a.source,
                "timestamp":       str(a.timestamp),
                "observed_value":  a.observed_value,
                "expected_value":  a.expected_value,
                "deviation_score": a.deviation_score,
                "severity":        a.severity,
                "method":          a.method,
            }
            for a in anomalies
        ],
    }


# ── Causal Investigation ──────────────────────────────────────────────────────

@router.post("/investigate")
def investigate(p=Depends(_pipeline)):
    anomalies = p.watchman.detect()
    report    = p.investigator.investigate(anomalies)
    return {
        "summary":     report.summary,
        "root_causes": [
            {
                "cause":      rc.cause_metric,
                "effect":     rc.effect_metric,
                "strength":   rc.causal_strength,
                "confidence": rc.confidence,
                "explanation": rc.explanation,
            }
            for rc in report.root_causes
        ],
        "cbmg": report.cbmg.to_dict(),
    }


# ── NL Report ─────────────────────────────────────────────────────────────────

@router.post("/report")
def generate_report(p=Depends(_pipeline)):
    anomalies  = p.watchman.detect()
    inv        = p.investigator.investigate(anomalies)
    report     = p.reporter.generate(anomalies, inv.root_causes)
    return {"report": report}


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts/history")
def alert_history(p=Depends(_pipeline)):
    return {"history": p.messenger.get_history()}


# ── Sample Data Seed (dev only) ───────────────────────────────────────────────

@router.post("/dev/seed")
def seed_sample_data(p=Depends(_pipeline)):
    import numpy as np
    import pandas as pd

    rng     = np.random.default_rng(42)
    periods = 336
    ts      = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=periods, freq="h")

    def spikes(arr, n=6):
        idx = rng.choice(len(arr), n, replace=False)
        arr[idx] *= rng.uniform(2.5, 4.0, n)
        return arr

    base = {
        "daily_revenue":       rng.normal(50_000, 2000, periods),
        "order_count":         rng.normal(300, 15, periods),
        "avg_order_value":     rng.normal(165, 8, periods),
        "customer_churn_rate": rng.normal(2.1, 0.15, periods),
        "cart_abandonment":    rng.normal(68, 3, periods),
        "nps_score":           rng.normal(42, 2, periods),
    }
    rows = []
    for name, values in base.items():
        values = spikes(np.abs(values))
        for t, v in zip(ts, values):
            rows.append(("sample_data", name, float(v), t))

    df = pd.DataFrame(rows, columns=["source", "metric_name", "value", "timestamp"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    p.collector._store(df)
    return {"seeded": len(df), "metrics": list(base.keys())}


# ── Full Pipeline ─────────────────────────────────────────────────────────────

@router.post("/pipeline/run")
def run_pipeline(p=Depends(_pipeline)):
    result = p.run()
    return {
        "metrics_collected": result["metrics_collected"],
        "anomalies_found":   len(result.get("anomalies", [])),
        "alert_sent":        result.get("alert_sent", False),
        "errors":            result.get("errors", []),
    }
