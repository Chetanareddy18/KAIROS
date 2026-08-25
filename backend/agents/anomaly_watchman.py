"""Agent 2: Anomaly Watchman — Prophet + Z-Score temporal anomaly detection."""
import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

logger = logging.getLogger("kairos.agent2")


@dataclass
class AnomalyResult:
    metric_name:     str
    source:          str
    timestamp:       datetime
    observed_value:  float
    expected_value:  float
    deviation_score: float
    method:          str       # "prophet" | "zscore"
    severity:        str       # "low" | "medium" | "high" | "critical"


class AnomalyWatchmanAgent:
    def __init__(self, db_path: str = "kairos.duckdb", z_threshold: float = 3.0):
        import duckdb
        self.conn        = duckdb.connect(db_path)
        self.z_threshold = z_threshold

    def detect(self) -> list[AnomalyResult]:
        pairs = self.conn.execute(
            "SELECT DISTINCT metric_name, source FROM metrics"
        ).fetchall()
        anomalies: list[AnomalyResult] = []
        for metric_name, source in pairs:
            df = self.conn.execute(
                "SELECT timestamp, value FROM metrics "
                "WHERE metric_name = ? AND source = ? ORDER BY timestamp",
                [metric_name, source],
            ).df()
            if len(df) < 10:
                continue
            anomalies.extend(self._analyse(df, metric_name, source))
        logger.info("Watchman: %d anomalies across %d metrics", len(anomalies), len(pairs))
        return anomalies

    def _analyse(self, df: pd.DataFrame, metric: str, source: str) -> list[AnomalyResult]:
        results: list[AnomalyResult] = []
        if len(df) >= 30:
            results.extend(self._prophet(df, metric, source))
        results.extend(self._zscore(df, metric, source))
        # deduplicate by timestamp, prefer prophet
        seen: set = set()
        unique   = []
        for r in results:
            key = (r.metric_name, str(r.timestamp))
            if key not in seen:
                seen.add(key)
                unique.append(r)
        return unique

    def _prophet(self, df: pd.DataFrame, metric: str, source: str) -> list[AnomalyResult]:
        try:
            from prophet import Prophet
            pdf = df.rename(columns={"timestamp": "ds", "value": "y"})
            pdf["ds"] = pd.to_datetime(pdf["ds"]).dt.tz_localize(None)
            m = Prophet(interval_width=0.99, weekly_seasonality=True, yearly_seasonality=False)
            m.fit(pdf)
            forecast  = m.predict(pdf[["ds"]])
            merged    = pdf.merge(forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]], on="ds")
            bad       = merged[(merged["y"] < merged["yhat_lower"]) | (merged["y"] > merged["yhat_upper"])]
            return [
                AnomalyResult(
                    metric_name=metric, source=source,
                    timestamp=row["ds"],
                    observed_value=row["y"], expected_value=row["yhat"],
                    deviation_score=abs(row["y"] - row["yhat"]) / (abs(row["yhat"]) + 1e-9),
                    method="prophet",
                    severity=self._severity(
                        abs(row["y"] - row["yhat"]) / (row["yhat_upper"] - row["yhat_lower"] + 1e-9)
                    ),
                )
                for _, row in bad.iterrows()
            ]
        except Exception as e:
            logger.warning("Prophet failed for '%s': %s", metric, e)
            return []

    def _zscore(self, df: pd.DataFrame, metric: str, source: str) -> list[AnomalyResult]:
        values        = df["value"]
        mean, std     = values.mean(), values.std()
        if std == 0:
            return []
        z = (values - mean) / std
        return [
            AnomalyResult(
                metric_name=metric, source=source,
                timestamp=df.iloc[i]["timestamp"],
                observed_value=float(df.iloc[i]["value"]),
                expected_value=float(mean),
                deviation_score=float(z.iloc[i]),
                method="zscore",
                severity=self._severity(abs(float(z.iloc[i]))),
            )
            for i in z[z.abs() >= self.z_threshold].index
        ]

    @staticmethod
    def _severity(score: float) -> str:
        if score >= 5.0: return "critical"
        if score >= 4.0: return "high"
        if score >= 3.0: return "medium"
        return "low"
