"""Builds every figure used in the capstone report and the two papers (300 DPI PNG).

    python docs/report/make_figures.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "figures"
OUT.mkdir(exist_ok=True)

TEAL, DARK, SAND, RED, GREY = "#1E7A78", "#0D3D3C", "#D4B896", "#C04040", "#6B7280"
LIGHT = "#EAF5F5"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "savefig.dpi": 300, "savefig.bbox": "tight"})


def box(ax, x, y, w, h, title, sub="", fc=LIGHT, ec=TEAL, tc=DARK, fs=9, bold=True):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.3))
    ax.text(x + w / 2, y + h / 2 + (0.13 if sub else 0), title, ha="center", va="center", color=tc,
            fontsize=fs, fontweight="bold" if bold else "normal")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.2, sub, ha="center", va="center", color=GREY, fontsize=fs - 2.2,
                linespacing=1.25)


def arrow(ax, x1, y1, x2, y2, color=TEAL, style="-|>", lw=1.3, ls="-", text=None, rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11, color=color, lw=lw,
                                 linestyle=ls, connectionstyle=f"arc3,rad={rad}"))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, ha="center", fontsize=6.8, color=GREY)


def canvas(w, h):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w * 1.5)
    ax.set_ylim(0, h * 1.5)
    ax.axis("off")
    return fig, ax


# ── Fig: system architecture ────────────────────────────────────────────────

def architecture():
    fig, ax = canvas(10, 6.6)
    W = 15
    ax.text(W / 2, 9.55, "KAIROS system architecture", ha="center", fontsize=12, fontweight="bold", color=DARK)
    # sources
    srcs = [("SQL databases", "PostgreSQL, MySQL,\nSnowflake, SQLite"), ("SFTP / FTP", "scheduled exports"),
            ("Files & cloud", "CSV, Excel, Parquet\nlocal, S3, HTTPS"), ("REST APIs", "SaaS, in-house"),
            ("Push / edge agent", "webhooks, large\nfiles at source")]
    for i, (t, s) in enumerate(srcs):
        box(ax, 0.3 + i * 2.95, 8.0, 2.65, 1.05, t, s, fc="white", ec=GREY, fs=8)
        arrow(ax, 1.62 + i * 2.95, 8.0, 1.62 + i * 2.95, 7.45, color=GREY)
    # ingestion layer
    box(ax, 0.3, 6.55, 14.4, 0.85, "Ingestion layer",
        "protocol adapters  ·  incremental watermarks  ·  aggregation push-down  ·  SLAC schema mapping  ·  "
        "Fast Transfer (chunked, parallel, resumable)", fc="#FBF7F0", ec=SAND, fs=9)
    # agents
    agents = [("Agent 1: Collector", "parallel pull,\nidempotent upsert"),
              ("Agent 2: Watchman", "robust seasonal z\n+ Prophet ensemble"),
              ("Agent 3: Investigator", "DYNOTEARS → CBMG\nDoWhy refinement"),
              ("Agent 4: Reporter", "Groq / Ollama LLM\nLLM-Modulo verifier"),
              ("Agent 5: Messenger", "Telegram, e-mail,\ndashboard history")]
    y = 4.35
    for i, (t, s) in enumerate(agents):
        x = 0.3 + i * 2.95
        box(ax, x, y, 2.65, 1.35, t, s, fc=LIGHT if i != 2 else "#D7EEEC", ec=TEAL if i != 2 else DARK, fs=7.6)
        if i < 4:
            arrow(ax, x + 2.65, y + 0.68, x + 2.95, y + 0.68)
    arrow(ax, 1.62, 6.55, 1.62, 5.7)
    ax.text(4.25 + 0.15, 4.15, "no new anomaly → stop", fontsize=6.8, color=GREY, ha="center")
    # orchestration and storage
    box(ax, 0.3, 3.05, 14.4, 0.8, "Orchestration: LangGraph state machine  ·  APScheduler (every 15 min, background thread)",
        fc="white", ec=TEAL, fs=8.5, bold=False)
    box(ax, 0.3, 1.85, 14.4, 0.8, "DuckDB store: metrics (key: source + metric + time) · anomalies · alerts · "
        "sources · connector state · runs · transfers", fc="white", ec=TEAL, fs=8, bold=False)
    # API + UI
    box(ax, 0.3, 0.3, 6.9, 1.1, "FastAPI REST API", "/pipeline · /sources · /ingest · /transfer · /investigate",
        fc=DARK, ec=DARK, tc="white", fs=9)
    box(ax, 7.8, 0.3, 6.9, 1.1, "React dashboard", "overview · causal graph · reports · data sources · fast transfer",
        fc=DARK, ec=DARK, tc="white", fs=9)
    arrow(ax, 7.2, 0.85, 7.8, 0.85, color=SAND, style="<|-|>")
    fig.savefig(OUT / "fig_architecture.png")
    plt.close(fig)


# ── Fig: LangGraph pipeline flow ────────────────────────────────────────────

def pipeline():
    fig, ax = canvas(10, 2.6)
    nodes = ["collect", "detect", "investigate", "report", "alert"]
    subs = ["sync all enabled\nsources in parallel", "score every series,\npersist anomalies",
            "DYNOTEARS on last 24 h,\nrank causal chains", "LLM draft → verify\n→ retry / template",
            "deliver, mark alerted,\nlog the run"]
    for i, (n, s) in enumerate(zip(nodes, subs)):
        x = 0.3 + i * 2.95
        box(ax, x, 1.45, 2.4, 1.3, n, s, fc=LIGHT if n != "investigate" else "#D7EEEC", fs=9)
        if i < 4:
            arrow(ax, x + 2.4, 2.1, x + 2.95, 2.1)
    ax.add_patch(FancyBboxPatch((6.2, 0.15), 2.4, 0.6, boxstyle="round,pad=0.02", fc="white", ec=GREY, lw=1))
    ax.text(7.4, 0.45, "END", ha="center", va="center", fontsize=8.5, color=GREY, fontweight="bold")
    arrow(ax, 4.45, 1.45, 6.2, 0.5, color=GREY, ls="--", rad=0.2)
    ax.text(2.3, 0.45, "no new alert-worthy anomaly\n(first sighting, ≥ min severity,\noutside cool-down)",
            fontsize=6.5, color=GREY, ha="center")
    fig.savefig(OUT / "fig_pipeline.png")
    plt.close(fig)


# ── Fig: ingestion decision strategy ────────────────────────────────────────

def ingestion():
    fig, ax = canvas(10, 4.4)
    box(ax, 3.9, 5.5, 7.2, 0.85, "Where does the data live, and how big is it?", fc=DARK, ec=DARK, tc="white", fs=9.5)
    routes = [
        ("Database table", "SQL push-down", "GROUP BY runs inside\nthe source; :since\nwatermark, new hours only",
         "100,305 rows → 19.5 KB"),
        ("Scheduled exports", "SFTP / FTP", "only files not seen\nbefore; .gz, .zst and\nParquet read directly",
         "14 old files skipped,\n1 new file\n(130 B) fetched"),
        ("Large raw files", "Edge agent", "DuckDB aggregates\nnext to the file;\npushes KPIs to /ingest",
         "106 MB → 94 KB\n(1,149× less)"),
        ("Raw file must move", "Fast Transfer", "chunks, zstd or gzip,\n8 streams, SHA-256,\nresume",
         "106 MB in 1.7 s;\nresume re-sends\nmissing chunks only"),
        ("SaaS / webhooks", "REST & push", "config-driven paging\nand auth headers;\nPOST /ingest",
         "no per-product\nconnector code"),
    ]
    for i, (q, t, how, res) in enumerate(routes):
        x = 0.25 + i * 2.95
        ax.text(x + 1.3, 4.65, q, ha="center", fontsize=7.6, color=GREY, style="italic")
        arrow(ax, 7.5, 5.5, x + 1.3, 4.9, color=GREY, lw=0.9)
        box(ax, x, 3.35, 2.6, 1.1, t, fc=LIGHT, fs=9.5)
        ax.text(x + 1.3, 2.75, how, ha="center", va="center", fontsize=6.6, color=DARK, linespacing=1.25)
        box(ax, x, 0.55, 2.6, 1.15, res, fc="#FBF7F0", ec=SAND, tc=DARK, fs=6.9, bold=True)
        arrow(ax, x + 1.3, 2.25, x + 1.3, 1.72, color=SAND)
    ax.text(7.5, 0.12, "measured results from the live demonstration (Chapter 4)", ha="center", fontsize=7, color=GREY)
    fig.savefig(OUT / "fig_ingestion.png")
    plt.close(fig)


# ── Fig: Fast Transfer protocol ─────────────────────────────────────────────

def transfer():
    fig, ax = plt.subplots(figsize=(9, 4.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10.4)
    ax.axis("off")
    for x, name in ((1.6, "Client\n(dashboard / edge agent)"), (8.4, "KAIROS server")):
        ax.add_patch(FancyBboxPatch((x - 1.5, 9.25), 3.0, 0.75, boxstyle="round,pad=0.02", fc=DARK, ec=DARK))
        ax.text(x, 9.62, name, ha="center", va="center", color="white", fontsize=7.6, fontweight="bold")
        ax.plot([x, x], [0.3, 9.25], color=GREY, lw=0.8, ls=":")
    steps = [
        (8.55, "→", "POST /transfer/start  {name, size, chunk size, SHA-256, codec}", ""),
        (7.85, "←", "transfer id + list of missing chunks (resumes a matching unfinished upload)", ""),
        (7.0, "→", "PUT /chunk/{n} × 8 in parallel   body = zstd(chunk)   header X-Chunk-SHA256", "parallel"),
        (6.3, "", "", "server: decompress → check length and hash → write at offset n·size → fsync → log n"),
        (5.4, "✕", "connection lost after 13 of 27 chunks", "drop"),
        (4.6, "→", "GET /transfer/{id}", ""),
        (3.9, "←", "missing = [13 … 26]", ""),
        (3.1, "→", "PUT only the 14 missing chunks", "parallel"),
        (2.2, "→", "POST /transfer/{id}/complete  {ingest: true}", ""),
        (1.4, "", "", "server: re-hash whole file, rename into place, SLAC infers mapping, DuckDB ingests"),
    ]
    for y, d, label, kind in steps:
        if d == "→":
            ax.annotate("", xy=(8.35, y), xytext=(1.65, y),
                        arrowprops=dict(arrowstyle="-|>", color=TEAL, lw=2.2 if kind == "parallel" else 1.2))
        elif d == "←":
            ax.annotate("", xy=(1.65, y), xytext=(8.35, y), arrowprops=dict(arrowstyle="-|>", color=SAND, lw=1.2))
        elif d == "✕":
            ax.plot([1.65, 4.8], [y, y], color=RED, lw=1.4)
            ax.text(5.0, y, "✕", color=RED, fontsize=13, va="center", fontweight="bold")
        if label:
            ax.text(5.0, y + (0.4 if d == "✕" else 0.22), label, ha="center", fontsize=7.4,
                    color=RED if d == "✕" else DARK)
        if kind and d == "":
            ax.text(8.25, y, kind, ha="right", fontsize=7, color=GREY, style="italic")
    fig.savefig(OUT / "fig_fast_transfer.png")
    plt.close(fig)


# ── Fig: Gantt chart ────────────────────────────────────────────────────────

def gantt():
    tasks = [
        ("Team formation, topic selection", 1, 2, "Planning"),
        ("Literature survey (ReAct, DYNOTEARS, LLM-Modulo)", 2, 4, "Planning"),
        ("Proposal & Evaluation 1", 4, 4, "Milestone"),
        ("Technology review, architecture design", 4, 6, "Design"),
        ("Agents 1–5, LangGraph pipeline, API", 5, 8, "Build"),
        ("React dashboard (v1)", 6, 8, "Build"),
        ("Mid-term review (Evaluation 2)", 8, 8, "Milestone"),
        ("Ingestion layer: adapters, SFTP, watermarks", 8, 10, "Build"),
        ("DYNOTEARS, SLAC mapping, LLM-Modulo verifier", 8, 10, "Build"),
        ("Edge agent, Fast Transfer, dashboard v2", 9, 11, "Build"),
        ("Testing, benchmarks, evaluation", 10, 12, "Test"),
        ("Report, papers, final evaluation", 11, 12, "Milestone"),
    ]
    colors = {"Planning": SAND, "Design": "#8FBFBD", "Build": TEAL, "Test": DARK, "Milestone": RED}
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for i, (name, a, b, kind) in enumerate(tasks):
        y = len(tasks) - i
        if a == b:
            ax.scatter([a + 0.5], [y], marker="D", s=55, color=colors[kind], zorder=3)
        else:
            ax.barh(y, b - a + 1, left=a, height=0.55, color=colors[kind], edgecolor="white")
        ax.text(0.85, y, name, ha="right", va="center", fontsize=7.8)
    ax.set_yticks([])
    ax.set_xlim(1, 13)
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels([f"W{w}" for w in range(1, 13)], fontsize=7.5)
    ax.set_xlabel("Semester week (7th semester, 2026)")
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color="#E5E7EB", lw=0.6)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors.values()]
    ax.legend(handles, colors.keys(), loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=5, frameon=False,
              fontsize=7.5)
    fig.savefig(OUT / "fig_gantt.png")
    plt.close(fig)


# ── Fig: ingestion benchmark ────────────────────────────────────────────────

def benchmark():
    data = json.loads((ROOT / "benchmark/results/results.json").read_text())
    rows = data["results"]
    labels = ["FTP raw", "FTP gzip", "Fast Transfer\ngzip", "Fast Transfer\nzstd", "Fast Transfer\nresumed",
              "Edge agent"][: len(rows)]
    secs = [r["seconds"] for r in rows]
    mb = [r["bytes_on_wire"] / 1048576 for r in rows]
    cols = [GREY, GREY, TEAL, TEAL, TEAL, DARK][: len(rows)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4))
    b = a1.bar(labels, secs, color=cols)
    a1.bar_label(b, fmt="%.1f s", fontsize=7)
    a1.set_ylabel("Wall-clock time (s)")
    a1.set_title("Time to move 2 M rows (106 MB CSV)", fontsize=9)
    b = a2.bar(labels, mb, color=cols)
    a2.set_yscale("log")
    a2.bar_label(b, labels=[f"{v:.1f} MB" if v >= 1 else f"{v * 1024:.0f} KB" for v in mb], fontsize=7)
    a2.set_ylabel("Bytes on the wire (MB, log scale)")
    a2.set_title("Data sent over the network", fontsize=9)
    for a in (a1, a2):
        a.tick_params(axis="x", labelsize=7)
    fig.text(0.5, -0.04, f"Each connection capped at {data['meta']['stream_mbps_cap']:g} Mbit/s (emulated WAN); "
             "8 streams × 4 MB chunks.", ha="center", fontsize=7.5, color=GREY)
    fig.tight_layout()
    fig.savefig(OUT / "fig_benchmark.png")
    plt.close(fig)


# ── Fig: anomaly detection example ──────────────────────────────────────────

def detection():
    from backend.demo.synthetic import generate
    from backend.models.anomaly import SEVERITY_ORDER, AnomalyDetectionPipeline
    df = generate(336, seed=3, end=pd.Timestamp("2026-10-01", tz="UTC"))
    det = AnomalyDetectionPipeline(use_prophet=False)
    sev_col = {"low": "#16A34A", "medium": "#CA8A04", "high": "#D97706", "critical": RED}
    fig, axes = plt.subplots(2, 2, figsize=(10, 4.8), sharex=True)
    for ax, m in zip(axes.ravel(), ["ad_spend_usd", "click_through_rate", "delivery_delay_hrs", "nps_score"]):
        s = df[df.metric_name == m].set_index("timestamp")["value"]
        ax.plot(s.index, s.values, color=TEAL, lw=0.8)
        for p in det.detect(s):
            ax.scatter(p.timestamp, p.value, color=sev_col[p.severity], s=16, zorder=3)
        ax.set_title(m, fontsize=8.5)
        ax.tick_params(labelsize=6.5)
    handles = [plt.Line2D([], [], marker="o", ls="", color=sev_col[k], label=k) for k in SEVERITY_ORDER]
    fig.legend(handles=handles, loc="lower center", ncol=4, frameon=False, fontsize=7.5, bbox_to_anchor=(0.5, -0.03))
    fig.autofmt_xdate()
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(OUT / "fig_detection.png")
    plt.close(fig)


# ── Fig: learned graph vs ground truth ──────────────────────────────────────

def causal_graph():
    import networkx as nx
    from backend.agents.causal_investigator import CausalInvestigatorAgent
    from backend.demo.synthetic import TRUE_EDGES, generate
    from backend.models.dynotears import dynotears
    df = generate(336, seed=3, end=pd.Timestamp("2026-10-01", tz="UTC"))
    data = df.pivot_table(index="timestamp", columns="metric_name", values="value").sort_index()
    cols = list(data.columns)
    r = dynotears(CausalInvestigatorAgent._prepare(data), p=1, lambda_w=0.05, lambda_a=0.05)
    d = len(cols)
    found = {}
    for i in range(d):
        for j in range(d):
            w = max(abs(r.W[i, j]), abs(r.A[i, j])) if i != j else 0
            if w >= 0.15:
                found[(cols[i], cols[j])] = w
    truth = {(c, e) for c, e, _, _ in TRUE_EDGES}
    g = nx.DiGraph()
    g.add_nodes_from(cols)
    g.add_edges_from(set(found) | truth)
    pos = {
        "ad_spend_usd": (0, 3), "click_through_rate": (1, 3), "conversion_rate": (2, 3), "cart_abandonment_rate": (1, 3.9),
        "order_count": (3, 3), "daily_revenue": (4, 3.5), "refund_count": (4, 2.5), "avg_order_value": (3, 3.9),
        "inventory_turnover": (0, 1), "delivery_delay_hrs": (1, 1), "support_tickets_open": (2, 1),
        "avg_response_time_hrs": (3, 1), "nps_score": (4, 1), "customer_churn_rate": (5, 1), "gross_margin_pct": (5, 3.9),
    }
    fig, ax = plt.subplots(figsize=(10, 4))
    tp = [e for e in found if e in truth]
    fp = [e for e in found if e not in truth]
    fn = [e for e in truth if e not in found]
    nx.draw_networkx_nodes(g, pos, node_color=LIGHT, edgecolors=TEAL, node_size=1500, ax=ax)
    nx.draw_networkx_labels(g, pos, labels={n: n.replace("_", "\n", 1) for n in g}, font_size=6, ax=ax)
    nx.draw_networkx_edges(g, pos, edgelist=tp, edge_color=TEAL, width=2, arrowsize=12, node_size=1500, ax=ax)
    nx.draw_networkx_edges(g, pos, edgelist=fp, edge_color=RED, width=1.4, style="dashed", node_size=1500, ax=ax)
    nx.draw_networkx_edges(g, pos, edgelist=fn, edge_color=GREY, width=1.2, style="dotted", node_size=1500, ax=ax)
    ax.legend(handles=[plt.Line2D([], [], color=TEAL, lw=2, label=f"recovered true edge ({len(tp)})"),
                       plt.Line2D([], [], color=RED, lw=1.4, ls="--", label=f"spurious edge ({len(fp)})"),
                       plt.Line2D([], [], color=GREY, lw=1.2, ls=":", label=f"missed true edge ({len(fn)})")],
              loc="lower center", ncol=3, frameon=False, fontsize=7.5, bbox_to_anchor=(0.5, -0.12))
    ax.axis("off")
    fig.savefig(OUT / "fig_causal_graph.png")
    plt.close(fig)


# ── Fig: causal method comparison + verifier (needs model_eval.json) ────────

def evaluation():
    p = ROOT / "benchmark/results/model_eval.json"
    if not p.exists():
        print("model_eval.json missing — skipping evaluation figures")
        return
    ev = json.loads(p.read_text())
    methods = [m for m, d in ev["causal"].items() if d.get("runs")]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.3), gridspec_kw={"width_ratios": [3, 1.3]})
    x = np.arange(len(methods))
    for k, (key, c) in enumerate((("precision", SAND), ("recall", "#8FBFBD"), ("f1", TEAL))):
        means = [ev["causal"][m][key]["mean"] for m in methods]
        stds = [ev["causal"][m][key]["std"] for m in methods]
        b = a1.bar(x + (k - 1) * 0.26, means, 0.26, yerr=stds, capsize=2, color=c, label=key.upper() if key == "f1" else key)
        a1.bar_label(b, fmt="%.2f", fontsize=6, padding=2)
    a1.set_xticks(x)
    a1.set_xticklabels([m.replace(" (", "\n(") for m in methods], fontsize=7.5)
    a1.set_ylim(0, 1.15)
    a1.set_title(f"Causal discovery vs ground truth ({len(ev['seeds'])} seeds)", fontsize=9)
    a1.legend(frameon=False, fontsize=7, ncol=3, loc="upper right")
    shd = [ev["causal"][m]["shd"]["mean"] for m in methods]
    b = a2.barh([m.split(" (")[0] for m in methods][::-1], shd[::-1], color=[TEAL if "DYNO" in m else GREY for m in methods][::-1])
    a2.bar_label(b, fmt="%.1f", fontsize=7)
    a2.set_title("Structural Hamming distance (lower is better)", fontsize=8.5)
    a2.tick_params(labelsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "fig_causal_eval.png")
    plt.close(fig)


if __name__ == "__main__":
    for f in (architecture, pipeline, ingestion, transfer, gantt, benchmark, detection, causal_graph, evaluation):
        f()
        print("ok", f.__name__)


# ── Column-width figures for the two-column IEEE paper (3.45 in wide) ───────

def paper_figures():
    COLW = 3.45
    # architecture, vertical
    fig, ax = plt.subplots(figsize=(COLW, 4.3))
    ax.set_xlim(0, 10); ax.set_ylim(0, 12.6); ax.axis("off")
    def b(x, y, w, h, t, s="", fc=LIGHT, ec=TEAL, tc=DARK, fs=6.6):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.12", fc=fc, ec=ec, lw=0.9))
        ax.text(x + w / 2, y + h / 2 + (0.2 if s else 0), t, ha="center", va="center", fontsize=fs, color=tc, fontweight="bold")
        if s:
            ax.text(x + w / 2, y + h / 2 - 0.28, s, ha="center", va="center", fontsize=fs - 1.3, color=GREY if tc == DARK else "#D8E6E5")
    def ar(x1, y1, x2, y2, c=TEAL):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=7, color=c, lw=0.9))
    b(0.1, 11.4, 9.8, 1.0, "Sources", "SQL · SFTP/FTP · files & S3 · REST · push / edge agent", fc="white", ec=GREY)
    ar(5, 11.4, 5, 11.0, GREY)
    b(0.1, 9.9, 9.8, 1.05, "Ingestion layer", "adapters · watermarks · push-down · SLAC · Fast Transfer", fc="#FBF7F0", ec=SAND)
    ar(5, 9.9, 5, 9.5)
    steps = [("1 Collect", "parallel, idempotent upsert"), ("2 Detect", "robust seasonal z (+ Prophet)"),
             ("3 Investigate", "DYNOTEARS → CBMG → ranked chains"), ("4 Report", "LLM draft → LLM-Modulo verifier"),
             ("5 Alert", "Telegram · e-mail · dashboard")]
    y = 8.55
    for i, (t, s) in enumerate(steps):
        b(1.2, y, 7.6, 0.9, t, s, fc="#D7EEEC" if i == 2 else LIGHT, ec=DARK if i == 2 else TEAL)
        if i < 4:
            ar(5, y, 5, y - 0.35)
        y -= 1.25
    ax.text(9.42, 7.3, "stop if\nno new\nanomaly", fontsize=4.6, color=GREY, ha="center", linespacing=1.1)
    b(0.1, 1.55, 9.8, 0.8, "LangGraph state machine · APScheduler (15 min)", fc="white", fs=6)
    b(0.1, 0.45, 4.8, 0.85, "DuckDB store", fc=DARK, ec=DARK, tc="white", fs=6.3)
    b(5.1, 0.45, 4.8, 0.85, "FastAPI + React UI", fc=DARK, ec=DARK, tc="white", fs=6.3)
    fig.savefig(OUT / "pfig_architecture.png"); plt.close(fig)

    ev = json.loads((ROOT / "benchmark/results/model_eval.json").read_text())
    methods = [m for m, d in ev["causal"].items() if d.get("runs")]
    short = {"DYNOTEARS (KAIROS)": "DYNOTEARS", "Granger (lagged OLS)": "Granger", "VARLiNGAM": "VARLiNGAM", "Pearson correlation": "Correlation"}
    fig, ax = plt.subplots(figsize=(COLW, 2.0))
    x = np.arange(len(methods))
    for k, (key, c) in enumerate((("precision", SAND), ("recall", "#8FBFBD"), ("f1", TEAL))):
        m_ = [ev["causal"][m][key]["mean"] for m in methods]; s_ = [ev["causal"][m][key]["std"] for m in methods]
        bb = ax.bar(x + (k - 1) * 0.26, m_, 0.26, yerr=s_, capsize=1.5, color=c, label={"f1": "F1"}.get(key, key.capitalize()), error_kw={"lw": 0.6})
        ax.bar_label(bb, fmt="%.2f", fontsize=4.6, padding=1)
    ax.set_xticks(x); ax.set_xticklabels([short[m] for m in methods], fontsize=6.3)
    ax.set_ylim(0, 1.18); ax.tick_params(axis="y", labelsize=6); ax.set_ylabel("Score", fontsize=6.5)
    ax.legend(frameon=False, fontsize=5.6, ncol=3, loc="upper right")
    fig.savefig(OUT / "pfig_causal.png"); plt.close(fig)

    data = json.loads((ROOT / "benchmark/results/results.json").read_text())["results"]
    labels = ["FTP raw", "FTP gzip", "FT gzip", "FT zstd", "FT resume", "Edge"][: len(data)]
    cols = [GREY, GREY, TEAL, TEAL, TEAL, DARK][: len(data)]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(COLW, 1.9))
    bb = a1.bar(labels, [r["seconds"] for r in data], color=cols); a1.bar_label(bb, fmt="%.1f", fontsize=4.8)
    a1.set_ylabel("Time (s)", fontsize=6.3)
    mb = [r["bytes_on_wire"] / 1048576 for r in data]
    bb = a2.bar(labels, mb, color=cols); a2.set_yscale("log")
    a2.bar_label(bb, labels=[f"{v:.0f}M" if v >= 1 else f"{v * 1024:.0f}K" for v in mb], fontsize=4.8)
    a2.set_ylabel("Bytes sent (MB, log)", fontsize=6.3)
    for a in (a1, a2):
        a.tick_params(axis="x", labelsize=5.2, rotation=55); a.tick_params(axis="y", labelsize=5.5)
    fig.tight_layout(pad=0.3)
    fig.savefig(OUT / "pfig_benchmark.png"); plt.close(fig)


if __name__ == "__main__" and "--paper" in sys.argv:
    paper_figures(); print("ok paper figures")
