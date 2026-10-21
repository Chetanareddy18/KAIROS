"""Root-cause origin localisation: KAIROS against baseline strategies on the synthetic benchmark.

    python benchmark/rca_baselines.py --seeds 10

Every strategy sees the same detector output (robust seasonal z-score, last 24 h) and must name the
incident origins. The ground truth is {ad_spend_usd, delivery_delay_hrs}.

  Largest deviation   the two metrics with the largest |z| (what a "top movers" dashboard shows)
  Earliest anomaly    the two metrics that turned anomalous first
  Correlation + rank  KAIROS ranking on a Pearson-correlation graph (|r| >= 0.3, both directions)
  Granger + rank      KAIROS ranking on a lagged-OLS Granger graph
  VARLiNGAM + rank    KAIROS ranking on a VARLiNGAM graph
  KAIROS (no boot.)   DYNOTEARS graph, KAIROS ranking, no bootstrap confidence
  KAIROS              DYNOTEARS graph, KAIROS ranking, 2 bootstrap refits (the shipped configuration)

Chain precision = share of the top-5 ranked causal chains whose every edge is a true edge.
Writes benchmark/results/rca_baselines.json and rca_baselines.md.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("KAIROS_LLM_ENABLED", "false")
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
for name in ("kairos", "cmdstanpy", "prophet"):
    logging.getLogger(name).setLevel(logging.ERROR)

from backend.agents.anomaly_watchman import AnomalyWatchmanAgent  # noqa: E402
from backend.agents.causal_investigator import CausalInvestigatorAgent  # noqa: E402
from backend.agents.data_collector import DataCollectorAgent  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.demo.synthetic import TRUE_EDGES, generate  # noqa: E402
from backend.models.dynotears import granger_matrix  # noqa: E402

END = pd.Timestamp("2026-10-01", tz="UTC")
PERIODS = 336
ORIGINS = {"ad_spend_usd", "delivery_delay_hrs"}
TRUE = {(c, e) for c, e, _w, _l in TRUE_EDGES}


class GrangerInvestigator(CausalInvestigatorAgent):
    def _discover(self, X):
        d = X.shape[1]
        G = granger_matrix(X, 1)
        np.fill_diagonal(G, 0)
        A = np.zeros((d, d))
        A[:d] = G
        return np.zeros((d, d)), A, "granger"


class VarlingamInvestigator(CausalInvestigatorAgent):
    def _discover(self, X):
        from causallearn.search.FCMBased.lingam import VARLiNGAM
        m = VARLiNGAM(lags=1)
        m.fit(X)
        B0, B1 = m.adjacency_matrices_[0], m.adjacency_matrices_[1]
        return B0.T, B1.T, "varlingam"


class CorrelationInvestigator(CausalInvestigatorAgent):
    def _discover(self, X):
        d = X.shape[1]
        C = np.corrcoef(X, rowvar=False)
        np.fill_diagonal(C, 0)
        C[np.abs(C) < 0.3] = 0
        return C, np.zeros((d, d)), "correlation"


def graph_strategy(cls, bootstrap: int = 0):
    def run(db, anomalies):
        rep = cls(db, lags=1, bootstrap=bootstrap).investigate(anomalies)
        top = rep.root_causes[:5]
        ok = [all(e in TRUE for e in zip(rc.path, rc.path[1:])) for rc in top]
        return set(rep.origins), (sum(ok) / len(ok) if ok else 0.0)
    return run


def largest_deviation(_db, anomalies):
    best: dict[str, float] = {}
    for a in anomalies:
        best[a.metric_name] = max(best.get(a.metric_name, 0.0), abs(a.deviation_score))
    return set(sorted(best, key=best.get, reverse=True)[:2]), None


def earliest_anomaly(_db, anomalies):
    first: dict[str, pd.Timestamp] = {}
    for a in anomalies:
        t = pd.Timestamp(a.timestamp)
        if a.metric_name not in first or t < first[a.metric_name]:
            first[a.metric_name] = t
    # ties broken by |z| so the choice is deterministic
    zmax = {a.metric_name: abs(a.deviation_score) for a in anomalies}
    return set(sorted(first, key=lambda m: (first[m], -zmax[m]))[:2]), None


STRATEGIES = {
    "Largest deviation (top movers)": largest_deviation,
    "Earliest anomaly": earliest_anomaly,
    "Correlation graph + ranking": graph_strategy(CorrelationInvestigator),
    "Granger graph + ranking": graph_strategy(GrangerInvestigator),
    "VARLiNGAM graph + ranking": graph_strategy(VarlingamInvestigator),
    "KAIROS without bootstrap": graph_strategy(CausalInvestigatorAgent, bootstrap=0),
    "KAIROS (DYNOTEARS + ranking)": graph_strategy(CausalInvestigatorAgent, bootstrap=2),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    a = ap.parse_args()
    seeds = list(range(1, a.seeds + 1))
    rows = {k: [] for k in STRATEGIES}
    for s in seeds:
        tmp = tempfile.mkdtemp()
        db = Database(os.path.join(tmp, "r.duckdb"))
        df = generate(PERIODS, seed=s, end=END)
        c = DataCollectorAgent(db)
        for src, part in df.groupby("source"):
            c.ingest_dataframe(src, part[["metric_name", "value", "timestamp"]])
        w = AnomalyWatchmanAgent(db, use_prophet=False)
        w.detect()
        anomalies = w.recent(24)
        for name, fn in STRATEGIES.items():
            t0 = time.perf_counter()
            got, chain_p = fn(db, anomalies)
            sec = time.perf_counter() - t0
            tp = len(got & ORIGINS)
            p = tp / len(got) if got else 0.0
            r = tp / len(ORIGINS)
            rows[name].append({"exact": float(got == ORIGINS), "precision": p, "recall": r,
                               "f1": 2 * p * r / (p + r) if p + r else 0.0,
                               "chain_precision": chain_p, "seconds": sec, "named": sorted(got)})
        db.close()
        print(f"seed {s}: " + " | ".join(f"{k.split()[0]}={sorted(v[-1]['named'])}" for k, v in rows.items()))

    def agg(v, k):
        xs = [r[k] for r in v if r[k] is not None]
        return {"mean": float(np.mean(xs)), "std": float(np.std(xs))} if xs else None

    out = {k: {m: agg(v, m) for m in ("exact", "precision", "recall", "f1", "chain_precision", "seconds")}
           for k, v in rows.items()}
    res = ROOT / "benchmark" / "results"
    (res / "rca_baselines.json").write_text(json.dumps({"seeds": seeds, "results": out, "runs": rows}, indent=2,
                                                       default=str))
    f = lambda d, pct=True: "—" if d is None else (f"{d['mean'] * 100:.1f} ± {d['std'] * 100:.1f}%" if pct
                                                   else f"{d['mean']:.2f} ± {d['std']:.2f}")
    L = ["# Root-cause origin localisation vs baselines", "",
         f"Synthetic benchmark, {len(seeds)} seeds; same detector output for every strategy.", "",
         "| Strategy | Exact origins | Origin precision | Origin recall | Origin F1 | Top-5 chain precision | Time (s) |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for k, d in out.items():
        L.append(f"| {k} | {f(d['exact'])} | {f(d['precision'])} | {f(d['recall'])} | {f(d['f1'])} | "
                 f"{f(d['chain_precision'])} | {f(d['seconds'], False)} |")
    L += ["", "Reproduce: `python benchmark/rca_baselines.py --seeds 10`"]
    (res / "rca_baselines.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
