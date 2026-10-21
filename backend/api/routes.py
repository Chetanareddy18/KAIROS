"""KAIROS — core API: status, metrics, anomalies, causal analysis, reports, alerts, pipeline."""
import importlib.util
import logging

import pandas as pd
from fastapi import APIRouter, Depends, Request

from backend.api.deps import dev_only, get_pipeline
from backend.config import settings
from backend.models.slac import SemanticLayerAutoConstructor

logger = logging.getLogger("kairos.api")
router = APIRouter()


def _has(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


_CAPABILITIES = {m: _has(m) for m in ("prophet", "dowhy", "causallearn", "paramiko", "zstandard", "groq", "ollama")}


# ── Meta ──────────────────────────────────────────────────────────────────────

@router.get("/status")
def status(request: Request, p=Depends(get_pipeline)):
    sched = getattr(request.app.state, "scheduler", None)
    job = sched.get_job("kairos_pipeline") if sched else None
    runs = p.runs(1)
    return {
        "status": "running", "version": "2.0.0", "env": settings.env, "agents": 5,
        "scheduler": {
            "enabled": job is not None, "interval_min": settings.pipeline_interval_min,
            "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
        },
        "pipeline_running": p.running,
        "last_run": runs[0] if runs else None,
        "data": p.collector.overview(),
        "anomalies": p.watchman.severity_counts(),
        "llm": {"groq": bool(settings.groq_api_key), "model": settings.groq_model, "enabled": settings.llm_enabled},
        "channels": p.messenger.channels,
        "capabilities": _CAPABILITIES,
        "auth_required": bool(settings.api_key),
    }


# ── Metrics ───────────────────────────────────────────────────────────────────

@router.get("/metrics")
def list_metrics(p=Depends(get_pipeline)):
    return {"metrics": p.collector.list_metrics()}


def _series_payload(p, metric_name: str, hours: int, source: str | None):
    df = p.collector.get_series(metric_name, hours, source)
    anomalies = p.watchman.list_anomalies(metric=metric_name, source=source, limit=2000)
    flagged = {(a["source"], a["timestamp"]): a for a in anomalies}
    points = []
    for r in df.itertuples():
        ts = pd.Timestamp(r.timestamp).isoformat()
        a = flagged.get((r.source, ts))
        points.append({"timestamp": ts, "value": r.value, "source": r.source,
                       "anomaly": a["severity"] if a else None,
                       "expected": a["expected_value"] if a else None})
    return {"metric": metric_name, "source": source, "points": points}


@router.get("/metrics/{metric_name}/series")
def get_series(metric_name: str, hours: int = 168, source: str | None = None, p=Depends(get_pipeline)):
    return _series_payload(p, metric_name, hours, source)


# ── Anomalies ─────────────────────────────────────────────────────────────────

@router.get("/anomalies")
def get_anomalies(severity: str | None = None, source: str | None = None, metric: str | None = None,
                  limit: int = 500, p=Depends(get_pipeline)):
    items = p.watchman.list_anomalies(severity, source, metric, limit)
    return {"count": len(items), "counts": p.watchman.severity_counts(), "anomalies": items}


@router.post("/anomalies/detect")
def detect_now(p=Depends(get_pipeline)):
    found = p.watchman.detect()
    return {"found": len(found), "new": sum(a.is_new for a in found), "counts": p.watchman.severity_counts()}


# ── Causal investigation ──────────────────────────────────────────────────────

@router.post("/investigate")
def investigate(hours: int = 24, p=Depends(get_pipeline)):
    recent = p.watchman.recent(hours)
    if not recent:
        p.watchman.detect()
        recent = p.watchman.recent(hours)
    report = p.investigator.investigate(recent)
    p.last_investigation = report
    return report.to_dict()


@router.get("/investigation/latest")
def latest_investigation(p=Depends(get_pipeline)):
    if p.last_investigation is None:
        return investigate(24, p)
    return p.last_investigation.to_dict()


# ── NL report ─────────────────────────────────────────────────────────────────

@router.post("/report")
def generate_report(hours: int = 24, p=Depends(get_pipeline)):
    recent = p.watchman.recent(hours)
    inv = p.last_investigation or p.investigator.investigate(recent)
    p.last_investigation = inv
    result = p.reporter.generate_report(recent, inv.root_causes, inv.origins)
    p.last_report = result.to_dict()
    return {"report": result.text, **result.to_dict()}


@router.get("/report/latest")
def latest_report(p=Depends(get_pipeline)):
    return p.last_report or {"report": "", "text": ""}


# ── Semantic layer ────────────────────────────────────────────────────────────

@router.get("/semantics")
def semantics(use_llm: bool = False, p=Depends(get_pipeline)):
    names = sorted(p.collector.get_all_metric_names())
    return SemanticLayerAutoConstructor().build(names, use_llm=use_llm)


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/alerts/history")
def alert_history(limit: int = 50, p=Depends(get_pipeline)):
    return {"history": p.messenger.get_history(limit), "channels": p.messenger.channels}


@router.post("/alerts/test")
def alert_test(p=Depends(get_pipeline)):
    ok = p.messenger.send("This is a KAIROS test alert — delivery channels are working.",
                          subject="KAIROS test alert", model="test")
    return {"delivered": ok, "channels": p.messenger.channels}


# ── Pipeline ──────────────────────────────────────────────────────────────────

@router.post("/pipeline/run")
def run_pipeline(p=Depends(get_pipeline)):
    return p.run(trigger="manual")


@router.get("/pipeline/runs")
def pipeline_runs(limit: int = 20, p=Depends(get_pipeline)):
    return {"runs": p.runs(limit)}


# ── Ingestion benchmark results (benchmark/benchmark_ingestion.py) ────────────

@router.get("/benchmark")
def benchmark_results():
    import json

    from backend.config import ROOT
    path = ROOT / "benchmark" / "results" / "results.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"results": []}


# ── Demo data (development only) ──────────────────────────────────────────────

@router.post("/dev/seed", dependencies=[Depends(dev_only)])
def seed_sample_data(reset: bool = True, p=Depends(get_pipeline)):
    """Two weeks of hourly data from 4 simulated sources with a known causal structure + incidents."""
    from backend.demo.synthetic import TRUE_EDGES, generate

    if reset:
        p.db.reset()
        p.last_investigation = None
        p.last_report = None
    df = generate()
    for source, part in df.groupby("source"):
        if p.collector.get_source(source) is None:
            p.collector.upsert_source(source, "push", {}, description="synthetic demo source", managed_by="demo")
        p.collector.ingest_dataframe(source, part[["metric_name", "value", "timestamp"]])
    return {
        "seeded": len(df),
        "sources": sorted(df["source"].unique().tolist()),
        "total_metrics": int(df["metric_name"].nunique()),
        "breakdown": {s: sorted(g["metric_name"].unique().tolist()) for s, g in df.groupby("source")},
        "ground_truth_edges": [{"from": c, "to": e, "weight": w, "lag": lag} for c, e, w, lag in TRUE_EDGES],
    }


@router.post("/dev/reset", dependencies=[Depends(dev_only)])
def reset_data(p=Depends(get_pipeline)):
    p.db.reset()
    p.last_investigation = None
    p.last_report = None
    return {"reset": True}


@router.get("/dev/ground-truth", dependencies=[Depends(dev_only)])
def ground_truth():
    from backend.demo.synthetic import TRUE_EDGES
    return {"edges": [{"from": c, "to": e, "weight": w, "lag": lag} for c, e, w, lag in TRUE_EDGES]}
