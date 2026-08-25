"""Agent 3: Causal Investigator — DYNOTEARS/VARLINGAM + DoWhy + CBMG builder."""
import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from backend.agents.anomaly_watchman import AnomalyResult
from backend.models.cbmg import CausalBusinessMetricGraph

logger = logging.getLogger("kairos.agent3")


@dataclass
class RootCause:
    cause_metric:    str
    effect_metric:   str
    causal_strength: float
    lag_hours:       int
    confidence:      float
    explanation:     str


@dataclass
class RootCauseReport:
    anomalies:   list[AnomalyResult]
    root_causes: list[RootCause]
    cbmg:        CausalBusinessMetricGraph
    summary:     str


class CausalInvestigatorAgent:
    def __init__(self, db_path: str = "kairos.duckdb"):
        import duckdb
        self.conn = duckdb.connect(db_path)

    def investigate(self, anomalies: list[AnomalyResult]) -> RootCauseReport:
        if not anomalies:
            return RootCauseReport([], [], CausalBusinessMetricGraph(), "No anomalies.")

        metric_names = list({a.metric_name for a in anomalies})
        data         = self._load_multivariate(metric_names)

        if data.empty or data.shape[1] < 2:
            return RootCauseReport(anomalies, [], CausalBusinessMetricGraph(), "Insufficient data for causal analysis.")

        adj = self._run_dynotears(data)
        cbmg = CausalBusinessMetricGraph()
        cols = data.columns.tolist()
        root_causes: list[RootCause] = []

        for i, col_i in enumerate(cols):
            for j, col_j in enumerate(cols):
                if i == j:
                    continue
                strength = float(abs(adj[i, j]))
                if strength > 0.1:
                    cbmg.add_edge(col_i, col_j, weight=strength)
                    if col_j in metric_names:
                        root_causes.append(RootCause(
                            cause_metric=col_i,
                            effect_metric=col_j,
                            causal_strength=strength,
                            lag_hours=1,
                            confidence=min(strength, 1.0),
                            explanation=f"{col_i} causally drives {col_j} (strength={strength:.3f})",
                        ))

        root_causes = self._dowhy_refine(data, root_causes)
        root_causes.sort(key=lambda r: r.causal_strength, reverse=True)

        top = root_causes[0].cause_metric if root_causes else "unknown"
        summary = (
            f"{len(anomalies)} anomalies in {', '.join(metric_names)}. "
            f"{len(root_causes)} causal links found. Top driver: {top}."
        )
        logger.info("Investigation complete: %d root causes", len(root_causes))
        return RootCauseReport(anomalies, root_causes, cbmg, summary)

    def _load_multivariate(self, metrics: list[str]) -> pd.DataFrame:
        frames = {}
        for m in metrics:
            df = self.conn.execute(
                "SELECT timestamp, value FROM metrics WHERE metric_name = ? ORDER BY timestamp", [m]
            ).df()
            if not df.empty:
                frames[m] = df.set_index("timestamp")["value"].resample("1H").mean()
        if not frames:
            return pd.DataFrame()
        return pd.DataFrame(frames).dropna()

    def _run_dynotears(self, data: pd.DataFrame) -> np.ndarray:
        try:
            from causallearn.search.FCMBased.lingam import VARLINGAM
            model = VARLINGAM()
            model.fit(data.values)
            return np.abs(model.adjacency_matrices_[0])
        except Exception as e:
            logger.warning("VARLINGAM failed (%s) — using correlation fallback", e)
            corr = data.corr().values
            np.fill_diagonal(corr, 0)
            return np.abs(corr)

    def _dowhy_refine(self, data: pd.DataFrame, causes: list[RootCause]) -> list[RootCause]:
        for rc in causes[:5]:
            try:
                from dowhy import CausalModel
                model      = CausalModel(data=data.reset_index(), treatment=rc.cause_metric,
                                         outcome=rc.effect_metric, common_causes=[])
                identified = model.identify_effect(proceed_when_unidentifiable=True)
                estimate   = model.estimate_effect(identified, method_name="backdoor.linear_regression")
                rc.causal_strength = abs(float(estimate.value))
                rc.confidence      = min(rc.causal_strength, 1.0)
            except Exception as e:
                logger.debug("DoWhy skipped for %s→%s: %s", rc.cause_metric, rc.effect_metric, e)
        return causes
