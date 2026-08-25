"""Unified anomaly detection pipeline — Prophet + Z-Score/IQR."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger("kairos.model.anomaly")


@dataclass
class AnomalyPoint:
    timestamp: pd.Timestamp
    value:     float
    expected:  float
    score:     float
    method:    str   # "prophet" | "zscore" | "iqr"


class AnomalyDetectionPipeline:
    def __init__(self, z_threshold: float = 3.0, iqr_multiplier: float = 1.5, use_prophet: bool = True):
        self.z_threshold    = z_threshold
        self.iqr_multiplier = iqr_multiplier
        self.use_prophet    = use_prophet
        self._mean = self._std = self._q1 = self._q3 = self._iqr = None
        self._prophet_model = None

    def fit(self, series: pd.Series) -> None:
        s = series.dropna()
        self._mean = float(s.mean())
        self._std  = float(s.std())
        self._q1   = float(s.quantile(0.25))
        self._q3   = float(s.quantile(0.75))
        self._iqr  = self._q3 - self._q1

        if self.use_prophet and len(s) >= 30:
            try:
                from prophet import Prophet
                df = s.reset_index()
                df.columns = ["ds", "y"]
                df["ds"]   = pd.to_datetime(df["ds"]).dt.tz_localize(None)
                m = Prophet(interval_width=0.99, daily_seasonality=True)
                m.fit(df)
                self._prophet_model = m
            except Exception as e:
                logger.warning("Prophet fit failed: %s", e)

    def detect(self, series: pd.Series) -> list[AnomalyPoint]:
        if self._mean is None:
            raise RuntimeError("Call fit() before detect()")
        results = self._zscore(series)
        if self._prophet_model:
            results.extend(self._prophet(series))
        # Deduplicate, highest score wins
        seen: set = set()
        unique: list[AnomalyPoint] = []
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            if r.timestamp not in seen:
                seen.add(r.timestamp)
                unique.append(r)
        return unique

    def _zscore(self, series: pd.Series) -> list[AnomalyPoint]:
        z = (series - self._mean) / (self._std + 1e-9)
        return [
            AnomalyPoint(timestamp=ts, value=float(v),
                         expected=self._mean, score=float(abs(z[ts])), method="zscore")
            for ts, v in series.items()
            if abs(z[ts]) >= self.z_threshold
        ]

    def _prophet(self, series: pd.Series) -> list[AnomalyPoint]:
        try:
            df = series.reset_index()
            df.columns = ["ds", "y"]
            df["ds"]   = pd.to_datetime(df["ds"]).dt.tz_localize(None)
            forecast   = self._prophet_model.predict(df[["ds"]])
            merged     = df.merge(forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]], on="ds")
            bad        = merged[(merged["y"] < merged["yhat_lower"]) | (merged["y"] > merged["yhat_upper"])]
            return [
                AnomalyPoint(
                    timestamp=row["ds"], value=row["y"], expected=row["yhat"],
                    score=abs(row["y"] - row["yhat"]) / (abs(row["yhat"]) + 1e-9),
                    method="prophet",
                )
                for _, row in bad.iterrows()
            ]
        except Exception as e:
            logger.warning("Prophet detect failed: %s", e)
            return []
