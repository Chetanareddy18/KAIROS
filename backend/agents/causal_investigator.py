"""Agent 3: Causal Investigator — DYNOTEARS temporal causal discovery -> CBMG ->
root-cause ranking (graph paths + temporal evidence) -> DoWhy effect estimates.

Why not correlation: correlation is symmetric and cannot say *which* metric
moved first. DYNOTEARS learns a directed, acyclic structural VAR including lags,
so "ad spend fell at 10:00 -> CTR fell at 11:00 -> conversions fell at 12:00"
is recovered as a chain with direction and delay.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from backend.agents.anomaly_watchman import AnomalyResult
from backend.config import settings
from backend.db import Database, get_db
from backend.models.anomaly import SEVERITY_ORDER
from backend.models.cbmg import CausalBusinessMetricGraph
from backend.models.dynotears import dynotears, granger_matrix

logger = logging.getLogger("kairos.agent3")

EDGE_THRESHOLD = 0.15
_MAX_ROWS = 1500


@dataclass
class RootCause:
    cause_metric:    str
    effect_metric:   str
    causal_strength: float           # product of standardised edge weights along the path, 0..1
    lag_hours:       float
    confidence:      float           # bootstrap stability of the path's edges, 0..1
    explanation:     str
    path:            list[str] = field(default_factory=list)
    cause_anomalous: bool = False    # the cause itself was anomalous just before the effect
    is_origin:       bool = False    # anomalous with no anomalous upstream cause
    effect_estimate: float | None = None   # DoWhy standardised effect (direct edges)
    score:           float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RootCauseReport:
    anomalies:   list[AnomalyResult]
    root_causes: list[RootCause]
    cbmg:        CausalBusinessMetricGraph
    summary:     str
    origins:     list[str] = field(default_factory=list)
    method:      str = "none"
    stats:       dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary, "method": self.method, "origins": self.origins, "stats": self.stats,
            "root_causes": [rc.to_dict() for rc in self.root_causes],
            "cbmg": self.cbmg.to_dict(),
            "anomaly_count": len(self.anomalies),
        }


def column_key(metric: str, source: str, duplicated: set[str]) -> str:
    return f"{metric}@{source}" if metric in duplicated else metric


class CausalInvestigatorAgent:
    def __init__(self, db: Database | str | None = None, lags: int | None = None, bootstrap: int = 2):
        self.db = db if isinstance(db, Database) else get_db(db) if isinstance(db, str) else get_db()
        self.lags = lags or settings.causal_lags
        self.bootstrap = bootstrap

    # ── public ───────────────────────────────────────────────────────────────

    def investigate(self, anomalies: list[AnomalyResult]) -> RootCauseReport:
        if not anomalies:
            return RootCauseReport([], [], CausalBusinessMetricGraph(), "No anomalies to investigate.")

        data, step_hours, keymap = self._load_matrix(anomalies)
        anomalous_cols = sorted({keymap[(a.source, a.metric_name)] for a in anomalies
                                 if (a.source, a.metric_name) in keymap})
        if data.shape[1] < 2 or len(data) < 30:
            return RootCauseReport(anomalies, [], CausalBusinessMetricGraph(),
                                   "Insufficient overlapping history for causal analysis.", method="none")

        X = self._prepare(data)
        cols = list(data.columns)
        W, A, method = self._discover(X)
        conf = self._stability(X, W, A) if method == "dynotears" else None

        cbmg = CausalBusinessMetricGraph()
        sev_by_col: dict[str, str] = {}
        times_by_col: dict[str, list[pd.Timestamp]] = defaultdict(list)
        for a in anomalies:
            k = keymap.get((a.source, a.metric_name))
            if k is None:
                continue
            times_by_col[k].append(pd.Timestamp(a.timestamp))
            if SEVERITY_ORDER.index(a.severity) >= SEVERITY_ORDER.index(sev_by_col.get(k, "low")):
                sev_by_col[k] = a.severity
        src_by_col = {v: s for (s, _m), v in keymap.items()}
        for c in cols:
            cbmg.add_node(c, anomalous=c in sev_by_col, severity=sev_by_col.get(c), source=src_by_col.get(c))

        d = len(cols)
        for i in range(d):
            for j in range(d):
                if i != j and abs(W[i, j]) >= EDGE_THRESHOLD:
                    cbmg.add_edge(cols[i], cols[j], weight=abs(W[i, j]), lag=0,
                                  confidence=conf[0][i, j] if conf else 1.0, sign=int(np.sign(W[i, j])))
                for k in range(A.shape[0] // d):
                    w = A[k * d + i, j]
                    if i != j and abs(w) >= EDGE_THRESHOLD:
                        cbmg.add_edge(cols[i], cols[j], weight=abs(w), lag=k + 1,
                                      confidence=conf[1][k * d + i, j] if conf else 1.0, sign=int(np.sign(w)))

        root_causes = self._rank(cbmg, anomalous_cols, times_by_col, step_hours)
        root_causes = self._dowhy_refine(data, cbmg, root_causes)
        origins = sorted({rc.cause_metric for rc in root_causes if rc.is_origin})
        if not origins:
            origins = [c for c in anomalous_cols
                       if not any(cbmg.graph.nodes[p].get("anomalous") for p in cbmg.get_ancestors(c))][:3]

        affected = sorted(set(anomalous_cols))
        top = root_causes[0] if root_causes else None
        summary = (
            f"{len(anomalies)} anomalies across {len(affected)} metrics. "
            f"Causal graph: {cbmg.graph.number_of_nodes()} metrics, {cbmg.graph.number_of_edges()} edges ({method}). "
            + (f"Most likely origin: {', '.join(origins)}. " if origins else "")
            + (f"Strongest chain: {' → '.join(top.path)} (strength {top.causal_strength:.2f}, "
               f"confidence {top.confidence:.0%})." if top else "No upstream causes found — anomalies look independent.")
        )
        logger.info("Investigation: %d root causes, method=%s", len(root_causes), method)
        return RootCauseReport(
            anomalies, root_causes, cbmg, summary, origins=origins, method=method,
            stats={"variables": d, "samples": len(data), "step_hours": step_hours, "lags": self.lags},
        )

    # ── data ─────────────────────────────────────────────────────────────────

    def _load_matrix(self, anomalies: list[AnomalyResult]) -> tuple[pd.DataFrame, float, dict]:
        raw = self.db.df(
            "SELECT source, metric_name, timestamp, value FROM ("
            "  SELECT *, row_number() OVER (PARTITION BY source, metric_name ORDER BY timestamp DESC) AS rn "
            "  FROM metrics) WHERE rn <= ?",
            [_MAX_ROWS],
        )
        if raw.empty:
            return pd.DataFrame(), 1.0, {}
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True)
        counts = raw.groupby("metric_name")["source"].nunique()
        duplicated = set(counts[counts > 1].index)
        raw["key"] = [column_key(m, s, duplicated) for m, s in zip(raw["metric_name"], raw["source"])]
        keymap = {(s, m): column_key(m, s, duplicated)
                  for s, m in raw[["source", "metric_name"]].drop_duplicates().itertuples(index=False)}

        steps = raw.sort_values("timestamp").groupby("key")["timestamp"].apply(lambda t: t.diff().median())
        step = steps.dropna().median() if not steps.dropna().empty else pd.Timedelta(hours=1)
        step = max(step, pd.Timedelta(minutes=1))
        raw["bucket"] = raw["timestamp"].dt.floor(step)
        wide = raw.pivot_table(index="bucket", columns="key", values="value", aggfunc="mean").sort_index()
        wide = wide.interpolate(limit=3, limit_direction="both")
        wide = wide.loc[:, wide.notna().mean() > 0.8].dropna()
        wide = wide.loc[:, wide.std() > 1e-12]

        # keep the variables most relevant to the anomalies when there are too many
        max_vars = settings.causal_max_vars
        if wide.shape[1] > max_vars:
            anom = [keymap[(a.source, a.metric_name)] for a in anomalies if (a.source, a.metric_name) in keymap]
            anom = [c for c in dict.fromkeys(anom) if c in wide.columns][:max_vars]
            others = [c for c in wide.columns if c not in anom]
            if anom and others:
                corr = wide.corr().abs()[anom].loc[others].max(axis=1).sort_values(ascending=False)
                others = list(corr.index)
            wide = wide[(anom + others)[:max_vars]]
        return wide, step / pd.Timedelta(hours=1), keymap

    @staticmethod
    def _prepare(data: pd.DataFrame) -> np.ndarray:
        """Winsorise the anomalies themselves away (structure should reflect normal behaviour), standardise."""
        X = data.to_numpy(dtype=float).copy()
        med = np.median(X, axis=0)
        mad = 1.4826 * np.median(np.abs(X - med), axis=0)
        mad = np.where(mad < 1e-12, X.std(axis=0) + 1e-12, mad)
        X = np.clip(X, med - 3.5 * mad, med + 3.5 * mad)
        return (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-12)

    # ── discovery ────────────────────────────────────────────────────────────

    def _discover(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, str]:
        d = X.shape[1]
        try:
            res = dynotears(X, p=self.lags, lambda_w=0.05, lambda_a=0.05)
            return res.W, res.A, "dynotears"
        except Exception as e:  # noqa: BLE001
            logger.warning("DYNOTEARS failed (%s) — trying VARLiNGAM", e)
        try:
            from causallearn.search.FCMBased.lingam import VARLiNGAM
            model = VARLiNGAM(lags=self.lags)
            model.fit(X)
            mats = model.adjacency_matrices_          # [B0, B1, ...], B[j, i]: i -> j
            W = mats[0].T
            A = np.vstack([m.T for m in mats[1:]]) if len(mats) > 1 else np.zeros((self.lags * d, d))
            return W, A, "varlingam"
        except Exception as e:  # noqa: BLE001
            logger.warning("VARLiNGAM unavailable (%s) — using lagged regression (Granger) fallback", e)
        G = granger_matrix(X, self.lags)
        np.fill_diagonal(G, 0)
        A = np.zeros((self.lags * d, d))
        A[:d] = G
        return np.zeros((d, d)), A, "granger"

    def _stability(self, X: np.ndarray, W: np.ndarray, A: np.ndarray):
        """Edge confidence = share of block-bootstrap refits (plus the full fit) that keep the edge."""
        T = X.shape[0]
        win = int(T * 0.75)
        if self.bootstrap <= 0 or win < 30:
            return None
        starts = np.linspace(0, T - win, self.bootstrap).astype(int)
        cw = (np.abs(W) >= EDGE_THRESHOLD).astype(float)
        ca = (np.abs(A) >= EDGE_THRESHOLD).astype(float)
        for s in starts:
            try:
                r = dynotears(X[s: s + win], p=self.lags, lambda_w=0.05, lambda_a=0.05)
            except Exception:  # noqa: BLE001
                continue
            cw += (np.abs(r.W) >= EDGE_THRESHOLD)
            ca += (np.abs(r.A) >= EDGE_THRESHOLD)
        n = 1 + len(starts)
        return cw / n, ca / n

    # ── ranking ──────────────────────────────────────────────────────────────

    def _rank(self, cbmg: CausalBusinessMetricGraph, anomalous: list[str],
              times: dict[str, list[pd.Timestamp]], step_hours: float) -> list[RootCause]:
        g = cbmg.graph
        out: list[RootCause] = []
        for effect in anomalous:
            if effect not in g:
                continue
            for cause in cbmg.get_ancestors(effect):
                path, strength, lag_steps = cbmg.strongest_path(cause, effect)
                if not path or strength < 0.02:
                    continue
                lag_h = lag_steps * step_hours
                evidence = self._preceded(times.get(cause, []), times.get(effect, []),
                                          lag_h + 2 * step_hours)
                edges = list(zip(path, path[1:]))
                confidence = float(np.mean([g[u][v]["confidence"] for u, v in edges]))
                anomalous_upstream = any(
                    g.nodes[p].get("anomalous") and self._preceded(times.get(p, []), times.get(cause, []),
                                                                   6 * step_hours)
                    for p in cbmg.get_ancestors(cause)
                )
                is_origin = evidence and not anomalous_upstream
                # geometric mean per hop, so a full origin→effect chain is not penalised for its length;
                # chains backed by temporal evidence, and those starting at the origin, rank first
                per_hop = strength ** (1.0 / len(edges))
                score = per_hop * confidence * (1.5 if evidence else 1.0) * (2.0 if is_origin else 1.0)                     * (1 + 0.05 * len(edges))
                signs = "".join("+" if g[u][v]["sign"] > 0 else "−" for u, v in edges)
                chain = " → ".join(path)
                expl = (f"{cause} {'moved abnormally before' if evidence else 'causally drives'} {effect} "
                        f"via {chain} (lag ≈ {lag_h:g}h, effect signs {signs}, strength {strength:.2f}).")
                out.append(RootCause(
                    cause_metric=cause, effect_metric=effect, causal_strength=round(strength, 4),
                    lag_hours=lag_h, confidence=round(confidence, 3), explanation=expl, path=path,
                    cause_anomalous=evidence, is_origin=is_origin,
                    score=round(score, 4),
                ))
        # top 3 explanations per effect
        out.sort(key=lambda r: r.score, reverse=True)
        per_effect: dict[str, int] = defaultdict(int)
        ranked = []
        for rc in out:
            if per_effect[rc.effect_metric] < 3:
                ranked.append(rc)
                per_effect[rc.effect_metric] += 1
        return ranked

    @staticmethod
    def _preceded(cause_times: list, effect_times: list, max_gap_h: float) -> bool:
        """Did the cause have an anomaly at most `max_gap_h` before (or at) any effect anomaly?"""
        if not cause_times or not effect_times:
            return False
        gap = pd.Timedelta(hours=max_gap_h)
        for te in effect_times:
            for tc in cause_times:
                if te - gap <= tc <= te:
                    return True
        return False

    # ── DoWhy ────────────────────────────────────────────────────────────────

    def _dowhy_refine(self, data: pd.DataFrame, cbmg: CausalBusinessMetricGraph,
                      causes: list[RootCause]) -> list[RootCause]:
        direct = [rc for rc in causes if len(rc.path) == 2][:5]
        if not direct:
            return causes
        try:
            import warnings
            warnings.filterwarnings("ignore")
            logging.getLogger("dowhy").setLevel(logging.ERROR)
            from dowhy import CausalModel
        except Exception:  # noqa: BLE001 — optional dependency
            return causes
        Z = (data - data.mean()) / (data.std() + 1e-12)
        for rc in direct:
            try:
                lag = int(cbmg.graph[rc.cause_metric][rc.effect_metric]["lag"])
                frame = pd.DataFrame({"treatment": Z[rc.cause_metric].shift(lag), "outcome": Z[rc.effect_metric]})
                parents = [p for p in cbmg.graph.predecessors(rc.effect_metric) if p != rc.cause_metric][:4]
                for i, p in enumerate(parents):
                    frame[f"w{i}"] = Z[p].shift(int(cbmg.graph[p][rc.effect_metric]["lag"]))
                frame = frame.dropna()
                model = CausalModel(data=frame, treatment="treatment", outcome="outcome",
                                    common_causes=[f"w{i}" for i in range(len(parents))] or None)
                estimand = model.identify_effect(proceed_when_unidentifiable=True)
                est = model.estimate_effect(estimand, method_name="backdoor.linear_regression")
                rc.effect_estimate = round(float(est.value), 4)
            except Exception as e:  # noqa: BLE001
                logger.debug("DoWhy skipped for %s→%s: %s", rc.cause_metric, rc.effect_metric, e)
        return causes
