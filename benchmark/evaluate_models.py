"""Model evaluation on the synthetic benchmark with known ground truth.

    python benchmark/evaluate_models.py --seeds 10

Writes benchmark/results/model_eval.json and model_eval.md.

  A. Causal discovery   DYNOTEARS vs Granger (lagged OLS) vs VARLiNGAM vs Pearson correlation,
                        scored against TRUE_EDGES: precision, recall, F1, structural Hamming distance.
  B. Root-cause origin  the full Agent 2 -> Agent 3 path: are the two injected incident origins
                        (ad_spend_usd, delivery_delay_hrs) the ones KAIROS reports?
  C. Anomaly detection  event-level recall and point-level precision of the robust detector,
                        with and without the Prophet ensemble.
  D. LLM-Modulo critic  how often the verifier catches corrupted numbers / invented metrics in a
                        report, and how often it wrongly rejects a faithful one.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
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

from backend.agents.causal_investigator import CausalInvestigatorAgent  # noqa: E402
from backend.agents.data_collector import DataCollectorAgent  # noqa: E402
from backend.agents.anomaly_watchman import AnomalyWatchmanAgent  # noqa: E402
from backend.agents.nl_reporter import NLReporterAgent  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.demo.synthetic import METRICS, TRUE_EDGES, generate  # noqa: E402
from backend.models.dynotears import dynotears, granger_matrix  # noqa: E402

END = pd.Timestamp("2026-10-01", tz="UTC")
PERIODS = 336
THRESH = 0.15
TRUE = {(c, e) for c, e, _w, _l in TRUE_EDGES}
ORIGINS = {"ad_spend_usd", "delivery_delay_hrs"}
MARKETING = ["ad_spend_usd", "click_through_rate", "conversion_rate", "order_count", "daily_revenue", "refund_count"]
OPERATIONS = ["delivery_delay_hrs", "support_tickets_open", "avg_response_time_hrs", "nps_score", "customer_churn_rate"]
POINTS = [("gross_margin_pct", 30), ("avg_order_value", 50), ("refund_count", 20),
          ("cart_abandonment_rate", 90), ("inventory_turnover", 120), ("gross_margin_pct", 200)]


def wide(df: pd.DataFrame) -> pd.DataFrame:
    return df.pivot_table(index="timestamp", columns="metric_name", values="value").sort_index()


def prepare(data: pd.DataFrame) -> np.ndarray:
    return CausalInvestigatorAgent._prepare(data)


def edges_from(W: np.ndarray, A: np.ndarray, cols: list[str]) -> set[tuple[str, str]]:
    d = len(cols)
    out = set()
    for i in range(d):
        for j in range(d):
            if i == j:
                continue
            if abs(W[i, j]) >= THRESH:
                out.add((cols[i], cols[j]))
            for k in range(A.shape[0] // d):
                if abs(A[k * d + i, j]) >= THRESH:
                    out.add((cols[i], cols[j]))
    return out


def score(found: set, truth: set = TRUE) -> dict:
    tp = len(found & truth)
    fp = len(found - truth)
    fn = len(truth - found)
    reversed_ = len({(b, a) for a, b in truth} & found)
    p = tp / len(found) if found else 0.0
    r = tp / len(truth)
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    # SHD: missing + extra edges, a reversed edge counted once rather than twice
    shd = fp + fn - reversed_
    return {"precision": p, "recall": r, "f1": f1, "shd": shd, "tp": tp, "fp": fp, "fn": fn, "edges": len(found)}


# ── A. causal discovery ──────────────────────────────────────────────────────

def method_dynotears(X, cols):
    r = dynotears(X, p=1, lambda_w=0.05, lambda_a=0.05)
    return edges_from(r.W, r.A, cols)


def method_granger(X, cols):
    G = granger_matrix(X, 1)
    np.fill_diagonal(G, 0)
    return edges_from(np.zeros_like(G), G, cols)


def method_varlingam(X, cols):
    from causallearn.search.FCMBased.lingam import VARLiNGAM
    m = VARLiNGAM(lags=1)
    m.fit(X)
    B0, B1 = m.adjacency_matrices_[0], m.adjacency_matrices_[1]
    return edges_from(B0.T, B1.T, cols)


def method_correlation(X, cols, thr=0.3):
    C = np.corrcoef(X, rowvar=False)
    out = set()
    for i in range(len(cols)):
        for j in range(len(cols)):
            if i != j and abs(C[i, j]) >= thr:
                out.add((cols[i], cols[j]))          # correlation has no direction: both ways
    return out


METHODS = {"DYNOTEARS (KAIROS)": method_dynotears, "Granger (lagged OLS)": method_granger,
           "VARLiNGAM": method_varlingam, "Pearson correlation": method_correlation}


def eval_causal(seeds: list[int]) -> dict:
    rows = {m: [] for m in METHODS}
    for s in seeds:
        data = wide(generate(PERIODS, seed=s, end=END))
        cols = list(data.columns)
        X = prepare(data)
        for name, fn in METHODS.items():
            t0 = time.perf_counter()
            try:
                found = fn(X, cols)
            except Exception as e:  # noqa: BLE001
                print(f"  {name} failed on seed {s}: {e}")
                continue
            sc = score(found)
            sc["seconds"] = time.perf_counter() - t0
            rows[name].append(sc)
        print(f"  causal seed {s}: " + ", ".join(f"{m.split()[0]} F1={rows[m][-1]['f1']:.2f}" for m in METHODS if rows[m]))
    return {m: summarise(v) for m, v in rows.items()}


def summarise(rows: list[dict]) -> dict:
    keys = rows[0].keys() if rows else []
    return {k: {"mean": float(np.mean([r[k] for r in rows])), "std": float(np.std([r[k] for r in rows]))}
            for k in keys} | {"runs": len(rows)}


# ── B + C. full pipeline: detection + origin localisation ────────────────────

def explained(metric: str, ts: pd.Timestamp, ts_index: pd.DatetimeIndex) -> bool:
    n = len(ts_index)
    a0, b0 = ts_index[n - 14], ts_index[n - 8]
    h = pd.Timedelta(hours=1)
    if metric in MARKETING and a0 - h <= ts <= a0 + 8 * h:
        return True
    if metric in OPERATIONS and b0 - h <= ts <= b0 + 8 * h:
        return True
    for m, back in POINTS:
        if m == metric and abs(ts - ts_index[n - back]) <= h:
            return True
    return False


def events(ts_index: pd.DatetimeIndex) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    n = len(ts_index)
    a0, b0 = ts_index[n - 14], ts_index[n - 8]
    h = pd.Timedelta(hours=1)
    ev = [(m, a0 - h, a0 + 8 * h) for m in MARKETING] + [(m, b0 - h, b0 + 8 * h) for m in OPERATIONS]
    ev += [(m, ts_index[n - back] - h, ts_index[n - back] + h) for m, back in POINTS]
    return ev


def eval_pipeline(seeds: list[int], use_prophet: bool, investigate: bool) -> dict:
    det, origin_rows = [], []
    for s in seeds:
        tmp = tempfile.mkdtemp()
        db = Database(os.path.join(tmp, "e.duckdb"))
        df = generate(PERIODS, seed=s, end=END)
        collector = DataCollectorAgent(db)
        for src, part in df.groupby("source"):
            collector.ingest_dataframe(src, part[["metric_name", "value", "timestamp"]])
        ts_index = pd.DatetimeIndex(sorted(df["timestamp"].unique()))
        watch = AnomalyWatchmanAgent(db, use_prophet=use_prophet)
        t0 = time.perf_counter()
        found = watch.detect()
        det_s = time.perf_counter() - t0
        flags = [(a.metric_name, pd.Timestamp(a.timestamp)) for a in found]
        ok = [explained(m, t, ts_index) for m, t in flags]
        hits = sum(any(m == em and lo <= t <= hi for m, t in flags) for em, lo, hi in events(ts_index))
        det.append({"precision": sum(ok) / len(ok) if ok else 0.0, "event_recall": hits / len(events(ts_index)),
                    "flags": len(flags), "seconds": det_s})
        if investigate:
            t0 = time.perf_counter()
            rep = CausalInvestigatorAgent(db).investigate(watch.recent(24))
            inv_s = time.perf_counter() - t0
            got = set(rep.origins)
            origin_rows.append({
                "exact": float(got == ORIGINS), "origin_recall": len(got & ORIGINS) / len(ORIGINS),
                "origin_precision": len(got & ORIGINS) / len(got) if got else 0.0, "seconds": inv_s,
            })
        db.close()
        print(f"  pipeline seed {s} prophet={use_prophet}: P={det[-1]['precision']:.2f} "
              f"R={det[-1]['event_recall']:.2f}" + (f" origins={sorted(got)}" if investigate else ""))
    return {"detection": summarise(det), "origins": summarise(origin_rows) if origin_rows else None}


# ── D. LLM-Modulo verifier ───────────────────────────────────────────────────

FAKE_METRICS = ["customer_lifetime_value", "net_promoter_index", "warehouse_utilisation", "marketing_roi"]


def eval_verifier(seeds: list[int], variants: int = 40) -> dict:
    rep = NLReporterAgent()
    rng = random.Random(7)
    clean_ok = clean_n = num_caught = num_n = name_caught = name_n = round_ok = round_n = 0
    for s in seeds:
        tmp = tempfile.mkdtemp()
        db = Database(os.path.join(tmp, "v.duckdb"))
        df = generate(PERIODS, seed=s, end=END)
        c = DataCollectorAgent(db)
        for src, part in df.groupby("source"):
            c.ingest_dataframe(src, part[["metric_name", "value", "timestamp"]])
        w = AnomalyWatchmanAgent(db, use_prophet=False)
        w.detect()
        recent = w.recent(24)
        inv = CausalInvestigatorAgent(db, bootstrap=0).investigate(recent)
        top = rep._top_anomalies(recent)
        allowed = rep._allowed_numbers(top, inv.root_causes, len(recent))
        known = {a.metric_name for a in recent} | {m for rc in inv.root_causes for m in rc.path}
        text = rep._template(top, inv.root_causes, inv.origins, len(recent))
        clean_n += 1
        clean_ok += not rep.verify(text, allowed, known)
        nums = [m for m in re.finditer(r"\d[\d,]*\.\d+", text)]
        for _ in range(variants):
            m = rng.choice(nums)
            val = float(m.group(0).replace(",", ""))
            bad = val * rng.choice([0.5, 0.7, 1.3, 1.6, 2.5]) + rng.choice([1.0, 3.0, 7.0])
            corrupted = text[:m.start()] + f"{bad:,.2f}" + text[m.end():]
            num_n += 1
            num_caught += bool(rep.verify(corrupted, allowed, known))
            # a faithful paraphrase that rounds the same number to one decimal must still pass
            rounded = text[:m.start()] + f"{val:,.1f}" + text[m.end():]
            round_n += 1
            round_ok += not rep.verify(rounded, allowed, known)
        names = sorted(known)
        for _ in range(variants // 4):
            real = rng.choice([n for n in names if n in text] or names)
            corrupted = text.replace(real, rng.choice(FAKE_METRICS), 1)
            name_n += 1
            name_caught += bool(rep.verify(corrupted, allowed, known))
        db.close()
    return {
        "faithful_reports_accepted": clean_ok / clean_n, "faithful_n": clean_n,
        "corrupted_numbers_caught": num_caught / num_n, "corrupted_numbers_n": num_n,
        "invented_metrics_caught": name_caught / name_n, "invented_metrics_n": name_n,
        "rounded_paraphrase_accepted": round_ok / round_n, "rounded_n": round_n,
    }


# ── report ───────────────────────────────────────────────────────────────────

def ms(d: dict, k: str, pct: bool = False, digits: int = 2) -> str:
    m, s = d[k]["mean"], d[k]["std"]
    return f"{m * 100:.1f} ± {s * 100:.1f}%" if pct else f"{m:.{digits}f} ± {s:.{digits}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--prophet-seeds", type=int, default=5)
    a = ap.parse_args()
    seeds = list(range(1, a.seeds + 1))

    print("A. causal discovery")
    causal = eval_causal(seeds)
    print("B/C. pipeline (robust detector + causal origins)")
    robust = eval_pipeline(seeds, use_prophet=False, investigate=True)
    print("C. pipeline with Prophet ensemble")
    prophet = eval_pipeline(seeds[: a.prophet_seeds], use_prophet=True, investigate=False)
    print("D. LLM-Modulo verifier")
    verifier = eval_verifier(seeds[:5])

    out = {"seeds": seeds, "periods": PERIODS, "metrics": len(METRICS), "true_edges": len(TRUE),
           "causal": causal, "pipeline_robust": robust, "pipeline_prophet": prophet, "verifier": verifier}
    res = ROOT / "benchmark" / "results"
    res.mkdir(parents=True, exist_ok=True)
    (res / "model_eval.json").write_text(json.dumps(out, indent=2))

    L = ["# KAIROS model evaluation", "",
         f"Synthetic benchmark: {len(METRICS)} metrics from 4 sources, {PERIODS} hourly points, "
         f"{len(TRUE)} ground-truth lagged causal edges, 2 injected incidents + 6 point anomalies. "
         f"Mean ± std over {len(seeds)} random seeds.", "",
         "## A. Causal discovery", "", "| Method | Precision | Recall | F1 | SHD | Edges | Time (s) |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for m, d in causal.items():
        if not d.get("runs"):
            continue
        L.append(f"| {m} | {ms(d, 'precision')} | {ms(d, 'recall')} | {ms(d, 'f1')} | {ms(d, 'shd', digits=1)} | "
                 f"{ms(d, 'edges', digits=1)} | {ms(d, 'seconds')} |")
    o = robust["origins"]
    L += ["", "## B. Root-cause origin localisation (Agent 2 → Agent 3)", "",
          f"- Both incident origins reported exactly: **{o['exact']['mean'] * 100:.0f}%** of runs",
          f"- Origin recall {ms(o, 'origin_recall', True)}, origin precision {ms(o, 'origin_precision', True)}",
          f"- Investigation time {ms(o, 'seconds')} s (DYNOTEARS + 2 bootstrap refits + DoWhy)", "",
          "## C. Anomaly detection", "", "| Detector | Event recall | Point precision | Flags | Time (s) | Seeds |",
          "|---|---:|---:|---:|---:|---:|"]
    for name, d in (("Robust seasonal z-score", robust["detection"]), ("Robust z + Prophet ensemble", prophet["detection"])):
        L.append(f"| {name} | {ms(d, 'event_recall', True)} | {ms(d, 'precision', True)} | {ms(d, 'flags', digits=1)} | "
                 f"{ms(d, 'seconds')} | {d['runs']} |")
    v = verifier
    L += ["", "## D. LLM-Modulo verifier", "",
          f"- Faithful reports accepted: {v['faithful_reports_accepted'] * 100:.0f}% (n={v['faithful_n']})",
          f"- Corrupted numbers caught: {v['corrupted_numbers_caught'] * 100:.1f}% (n={v['corrupted_numbers_n']})",
          f"- Invented metric names caught: {v['invented_metrics_caught'] * 100:.1f}% (n={v['invented_metrics_n']})",
          f"- Faithful one-decimal rounding accepted: {v['rounded_paraphrase_accepted'] * 100:.1f}% (n={v['rounded_n']})",
          "", "Reproduce: `python benchmark/evaluate_models.py --seeds 10`"]
    (res / "model_eval.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    main()
