"""Anomaly detection ensemble used by Agent 2.

Two complementary detectors, both expressed in the same unit (robust sigmas), so
severity means the same thing whichever detector fired:

* Seasonal robust z-score — expected value = rolling median + hour-of-day
  seasonal profile; sigma = 1.4826 x MAD of the residuals. Robust to the very
  outliers it is looking for, fast, no fitting.
* Prophet — trend + daily/weekly seasonality forecast; sigma derived from the
  99% interval. Used when installed and the series is long enough.

A point is anomalous when |score| >= threshold for either detector; when both
agree the method is reported as "prophet+robust_z" (higher confidence).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger("kairos.model.anomaly")
for _noisy in ("cmdstanpy", "prophet", "prophet.plot"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

_Z99 = 2.5758   # z for a 99% two-sided interval

SEVERITY_ORDER = ["low", "medium", "high", "critical"]


def severity_for(score: float) -> str:
    s = abs(score)
    if s >= 9.0:
        return "critical"
    if s >= 6.0:
        return "high"
    if s >= 4.5:
        return "medium"
    return "low"


def severity_at_least(severity: str, minimum: str) -> bool:
    return SEVERITY_ORDER.index(severity) >= SEVERITY_ORDER.index(minimum)


@dataclass
class AnomalyPoint:
    timestamp: pd.Timestamp
    value:     float
    expected:  float
    score:     float          # signed, in robust sigmas
    method:    str            # "robust_z" | "prophet" | "prophet+robust_z"

    @property
    def severity(self) -> str:
        return severity_for(self.score)


def _mad_sigma(x: np.ndarray) -> float:
    x = x[~np.isnan(x)]
    if len(x) == 0:
        return 0.0
    mad = np.median(np.abs(x - np.median(x)))
    sigma = 1.4826 * mad
    return float(sigma if sigma > 1e-12 else np.std(x))


def robust_baseline(series: pd.Series) -> tuple[pd.Series, float]:
    """Expected values (rolling median + hour-of-day seasonality) and robust sigma."""
    n      = len(series)
    window = int(max(5, min(25, n // 4)) | 1)            # odd window
    trend  = series.rolling(window, center=True, min_periods=max(3, window // 3)).median()
    trend  = trend.bfill().ffill()
    resid  = series - trend
    expected = trend.copy()

    idx = series.index
    if isinstance(idx, pd.DatetimeIndex) and n >= 72:
        step = pd.Series(idx).diff().median()
        if pd.notna(step) and step <= pd.Timedelta(hours=1):
            hour    = idx.hour
            profile = resid.groupby(hour).median()
            seasonal = pd.Series(profile.reindex(hour).to_numpy(), index=idx)
            # keep the seasonal term only if it explains a meaningful share of variation
            if _mad_sigma((resid - seasonal).to_numpy()) < 0.9 * _mad_sigma(resid.to_numpy()):
                expected = expected + seasonal
    sigma = _mad_sigma((series - expected).to_numpy())
    return expected, sigma


class AnomalyDetectionPipeline:
    def __init__(self, z_threshold: float = 3.5, use_prophet: bool = True, min_points: int = 10):
        self.z_threshold = z_threshold
        self.use_prophet = use_prophet
        self.min_points  = min_points

    def detect(self, series: pd.Series) -> list[AnomalyPoint]:
        """`series`: values indexed by timestamp (sorted)."""
        s = series.dropna().astype(float)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        if len(s) < self.min_points:
            return []

        expected, sigma = robust_baseline(s)
        robust_scores = (s - expected) / sigma if sigma > 0 else pd.Series(0.0, index=s.index)

        prophet = self._prophet(s) if self.use_prophet and len(s) >= 48 else None

        out: list[AnomalyPoint] = []
        for ts in s.index:
            rz  = float(robust_scores.loc[ts])
            r_hit = abs(rz) >= self.z_threshold
            p_hit, pz, p_exp = False, 0.0, None
            if prophet is not None and ts in prophet.index:
                p_exp, p_sigma = prophet.loc[ts, "yhat"], prophet.loc[ts, "sigma"]
                if p_sigma > 0:
                    pz = float((s.loc[ts] - p_exp) / p_sigma)
                    p_hit = abs(pz) >= self.z_threshold
            if not (r_hit or p_hit):
                continue
            if r_hit and p_hit:
                method, score, exp = "prophet+robust_z", rz if abs(rz) >= abs(pz) else pz, float(p_exp)
            elif r_hit:
                method, score, exp = "robust_z", rz, float(expected.loc[ts])
            else:
                method, score, exp = "prophet", pz, float(p_exp)
            out.append(AnomalyPoint(timestamp=ts, value=float(s.loc[ts]), expected=exp,
                                    score=score, method=method))
        return out

    @staticmethod
    def _prophet(s: pd.Series) -> pd.DataFrame | None:
        try:
            from prophet import Prophet
        except Exception:  # noqa: BLE001 — optional dependency
            return None
        try:
            logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
            logging.getLogger("prophet").setLevel(logging.WARNING)
            idx = pd.DatetimeIndex(s.index)
            ds  = idx.tz_convert("UTC").tz_localize(None) if idx.tz is not None else idx
            df  = pd.DataFrame({"ds": ds, "y": s.to_numpy()})
            span_days = (ds.max() - ds.min()).days
            m = Prophet(interval_width=0.99, daily_seasonality=True,
                        weekly_seasonality=span_days >= 14, yearly_seasonality=False)
            m.fit(df)
            fc = m.predict(df[["ds"]])
            out = pd.DataFrame({
                "yhat":  fc["yhat"].to_numpy(),
                "sigma": ((fc["yhat_upper"] - fc["yhat_lower"]) / (2 * _Z99)).to_numpy(),
            }, index=s.index)
            return out
        except Exception as e:  # noqa: BLE001
            logger.warning("Prophet failed, using robust detector only: %s", e)
            return None
