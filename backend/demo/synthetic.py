"""Synthetic multi-source business data with a *known* causal structure.

Because the true graph is known, the demo doubles as an evaluation: KAIROS
should detect the injected incidents and DYNOTEARS should recover the chains.

Ground-truth causal chains (lag 1 step = 1 hour):
  marketing : ad_spend_usd -> click_through_rate -> conversion_rate -> order_count -> daily_revenue
              cart_abandonment_rate -(neg)-> conversion_rate ; avg_order_value -> daily_revenue
              order_count -> refund_count
  operations: inventory_turnover -(neg)-> delivery_delay_hrs -> support_tickets_open
              -> avg_response_time_hrs -(neg)-> nps_score -(neg)-> customer_churn_rate
  independent: gross_margin_pct

Injected incidents (inside the last 24 h so they trigger alerts):
  A. ad_spend_usd collapses for 3 h  -> propagates down the marketing chain
  B. delivery_delay_hrs spikes for 3 h -> propagates down the operations chain
  plus isolated point anomalies of every severity on other metrics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# metric: (source, mean, sd)
METRICS = {
    "ad_spend_usd":          ("csv_marketing",      3200.0, 380.0),
    "click_through_rate":    ("csv_marketing",      2.4,    0.25),
    "conversion_rate":       ("csv_marketing",      3.1,    0.30),
    "cart_abandonment_rate": ("csv_marketing",      68.0,   2.5),
    "order_count":           ("postgresql_erp",     300.0,  18.0),
    "daily_revenue":         ("postgresql_erp",     50000., 2600.0),
    "avg_order_value":       ("postgresql_erp",     165.0,  6.0),
    "refund_count":          ("postgresql_erp",     12.0,   2.0),
    "gross_margin_pct":      ("postgresql_erp",     42.0,   1.5),
    "inventory_turnover":    ("rest_api_logistics", 8.5,    0.5),
    "delivery_delay_hrs":    ("rest_api_logistics", 1.2,    0.25),
    "support_tickets_open":  ("google_sheets_cs",   45.0,   6.0),
    "avg_response_time_hrs": ("google_sheets_cs",   3.2,    0.4),
    "nps_score":             ("google_sheets_cs",   42.0,   2.0),
    "customer_churn_rate":   ("google_sheets_cs",   2.1,    0.15),
}

# (cause, effect, coefficient on standardised scale, lag)
TRUE_EDGES = [
    ("ad_spend_usd", "click_through_rate", 0.75, 1),
    ("click_through_rate", "conversion_rate", 0.75, 1),
    ("cart_abandonment_rate", "conversion_rate", -0.45, 1),
    ("conversion_rate", "order_count", 0.8, 1),
    ("order_count", "daily_revenue", 0.8, 1),
    ("avg_order_value", "daily_revenue", 0.45, 1),
    ("order_count", "refund_count", 0.5, 1),
    ("inventory_turnover", "delivery_delay_hrs", -0.5, 1),
    ("delivery_delay_hrs", "support_tickets_open", 0.75, 1),
    ("support_tickets_open", "avg_response_time_hrs", 0.75, 1),
    ("avg_response_time_hrs", "nps_score", -0.75, 1),
    ("nps_score", "customer_churn_rate", -0.75, 1),
]

DAILY_SEASONAL = {"ad_spend_usd": 0.6, "order_count": 0.5, "daily_revenue": 0.5, "support_tickets_open": 0.4}


def generate(periods: int = 336, seed: int = 42, end: pd.Timestamp | None = None,
             incidents: bool = True) -> pd.DataFrame:
    """Hourly long-format frame: source, metric_name, timestamp, value."""
    rng   = np.random.default_rng(seed)
    names = list(METRICS)
    idx   = {n: i for i, n in enumerate(names)}
    d     = len(names)
    B     = np.zeros((d, d))
    for c, e, w, _lag in TRUE_EDGES:
        B[idx[c], idx[e]] = w

    end = (end or pd.Timestamp.now(tz="UTC")).floor("h")
    ts  = pd.date_range(end=end, periods=periods, freq="h")
    shocks = np.zeros((periods, d))
    if incidents:
        a0, b0 = periods - 14, periods - 8
        shocks[a0:a0 + 3, idx["ad_spend_usd"]] = -9.0
        shocks[b0:b0 + 3, idx["delivery_delay_hrs"]] = 9.0

    Z = np.zeros((periods, d))
    noise = rng.normal(0, 0.55, (periods, d))
    for t in range(1, periods):
        Z[t] = 0.25 * Z[t - 1] + Z[t - 1] @ B + noise[t] + shocks[t]
    hours = ts.hour.to_numpy()
    for name, amp in DAILY_SEASONAL.items():
        Z[:, idx[name]] += amp * np.sin(2 * np.pi * (hours - 9) / 24)

    if incidents:
        # isolated point anomalies with graded severity (in robust sigmas of the series)
        for name, t_back, k in [
            ("gross_margin_pct", 30, -12.0), ("avg_order_value", 50, 7.0),
            ("refund_count", 20, 5.0), ("cart_abandonment_rate", 90, 4.2),
            ("inventory_turnover", 120, -6.5), ("gross_margin_pct", 200, 4.0),
        ]:
            Z[periods - t_back, idx[name]] += k

    rows = []
    for name in names:
        source, mean, sd = METRICS[name]
        values = mean + sd * Z[:, idx[name]]
        values = np.maximum(values, mean * 0.02)
        rows.append(pd.DataFrame({"source": source, "metric_name": name, "timestamp": ts, "value": values}))
    return pd.concat(rows, ignore_index=True)


def generate_transactions(n_rows: int, days: int = 14, seed: int = 7, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Raw order-level records (what a company's ERP actually holds) for push-down / edge demos."""
    rng = np.random.default_rng(seed)
    end = (end or pd.Timestamp.now(tz="UTC")).floor("h")
    start = end - pd.Timedelta(days=days)
    secs = rng.integers(0, int((end - start).total_seconds()), n_rows)
    ts = (start + pd.to_timedelta(np.sort(secs), unit="s"))
    amount = np.round(rng.lognormal(mean=5.0, sigma=0.45, size=n_rows), 2)
    return pd.DataFrame({
        "order_id": np.arange(1, n_rows + 1),
        "created_at": ts.strftime("%Y-%m-%d %H:%M:%S"),
        "customer_id": rng.integers(1, max(2, n_rows // 5), n_rows),
        "region": rng.choice(["north", "south", "east", "west"], n_rows),
        "status": rng.choice(["paid", "paid", "paid", "refunded"], n_rows),
        "amount": amount,
        "items": rng.integers(1, 6, n_rows),
    })
