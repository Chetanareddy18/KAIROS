"""Sensitivity of the fixed thresholds: DYNOTEARS edge threshold / L1 penalty, and detection z threshold.

    python benchmark/sensitivity.py --seeds 10      -> benchmark/results/sensitivity.json / .md
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "benchmark"))

import evaluate_models as E  # noqa: E402
from backend.models.anomaly import AnomalyDetectionPipeline  # noqa: E402
from backend.models.dynotears import dynotears  # noqa: E402


def causal(seeds, lambdas, taus):
    out = {}
    for lam in lambdas:
        fits = []
        for s in seeds:
            data = E.wide(E.generate(E.PERIODS, seed=s, end=E.END))
            r = dynotears(E.prepare(data), p=1, lambda_w=lam, lambda_a=lam)
            fits.append((r, list(data.columns)))
        for tau in taus:
            E.THRESH = tau
            f1 = [E.score(E.edges_from(r.W, r.A, cols))["f1"] for r, cols in fits]
            out[f"{lam}|{tau}"] = {"lambda": lam, "tau": tau, "f1_mean": float(np.mean(f1)), "f1_std": float(np.std(f1))}
            print(f"  lambda={lam} tau={tau}: F1 {np.mean(f1):.3f} ± {np.std(f1):.3f}")
    E.THRESH = 0.15
    return out


def detection(seeds, zs):
    out = {}
    for z in zs:
        det = AnomalyDetectionPipeline(z_threshold=z, use_prophet=False)
        P, R = [], []
        for s in seeds:
            df = E.generate(E.PERIODS, seed=s, end=E.END)
            ts_index = pd.DatetimeIndex(sorted(df["timestamp"].unique()))
            flags = []
            for m, g in df.groupby("metric_name"):
                series = g.set_index("timestamp")["value"].sort_index()
                flags += [(m, pd.Timestamp(p.timestamp)) for p in det.detect(series)]
            ok = [E.explained(m, t, ts_index) for m, t in flags]
            ev = E.events(ts_index)
            P.append(sum(ok) / len(ok) if ok else 0.0)
            R.append(sum(any(m == em and lo <= t <= hi for m, t in flags) for em, lo, hi in ev) / len(ev))
        out[str(z)] = {"z": z, "precision": float(np.mean(P)), "recall": float(np.mean(R)),
                       "precision_std": float(np.std(P))}
        print(f"  z={z}: precision {np.mean(P):.3f} recall {np.mean(R):.3f}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    a = ap.parse_args()
    seeds = list(range(1, a.seeds + 1))
    print("causal sensitivity")
    c = causal(seeds, [0.01, 0.05, 0.1], [0.10, 0.15, 0.20, 0.30])
    print("detection sensitivity")
    d = detection(seeds, [3.0, 3.5, 4.0, 4.5, 5.0])
    res = ROOT / "benchmark" / "results"
    (res / "sensitivity.json").write_text(json.dumps({"seeds": seeds, "causal": c, "detection": d}, indent=2))
    lines = ["# Threshold sensitivity", "", f"Mean over {len(seeds)} seeds.", "", "## DYNOTEARS F1 by L1 penalty (rows) and edge threshold (columns)", "",
             "| lambda | " + " | ".join(f"tau={t}" for t in [0.10, 0.15, 0.20, 0.30]) + " |", "|---|" + "---:|" * 4]
    for lam in [0.01, 0.05, 0.1]:
        lines.append(f"| {lam} | " + " | ".join(f"{c[f'{lam}|{t}']['f1_mean']:.3f}" for t in [0.10, 0.15, 0.20, 0.30]) + " |")
    lines += ["", "## Detection by z threshold", "", "| z | precision | event recall |", "|---:|---:|---:|"]
    for z, v in d.items():
        lines.append(f"| {z} | {v['precision']:.3f} | {v['recall']:.3f} |")
    (res / "sensitivity.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
