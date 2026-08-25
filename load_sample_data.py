"""Loads 2 weeks of synthetic business metrics into DuckDB with built-in anomalies."""
import duckdb
import numpy as np
import pandas as pd
from datetime import datetime, timezone

rng  = np.random.default_rng(42)
conn = duckdb.connect("kairos.duckdb")

conn.execute("""
CREATE TABLE IF NOT EXISTS metrics (
    id          VARCHAR DEFAULT gen_random_uuid(),
    source      VARCHAR      NOT NULL,
    metric_name VARCHAR      NOT NULL,
    value       DOUBLE       NOT NULL,
    timestamp   TIMESTAMPTZ  NOT NULL,
    ingested_at TIMESTAMPTZ  DEFAULT now()
)
""")

periods = 336          # 2 weeks hourly
ts = pd.date_range(end=pd.Timestamp.now(tz="UTC"), periods=periods, freq="h")

def inject_spikes(arr, n=6):
    idx = rng.choice(len(arr), n, replace=False)
    arr[idx] *= rng.uniform(2.5, 4.0, n)
    return arr

metrics = {
    "daily_revenue":      50_000 + rng.normal(0, 2000, periods).cumsum() * 0 + rng.normal(50_000, 2000, periods),
    "order_count":        300    + rng.normal(0, 15,   periods),
    "avg_order_value":    165    + rng.normal(0, 8,    periods),
    "customer_churn_rate": 2.1   + rng.normal(0, 0.15, periods),
    "cart_abandonment":   68     + rng.normal(0, 3,    periods),
    "nps_score":          42     + rng.normal(0, 2,    periods),
}

rows = []
for name, values in metrics.items():
    values = inject_spikes(np.abs(values))
    for t, v in zip(ts, values):
        rows.append(("sample_data", name, float(v), t))

df = pd.DataFrame(rows, columns=["source", "metric_name", "value", "timestamp"])
conn.execute("INSERT INTO metrics (source, metric_name, value, timestamp) SELECT source, metric_name, value, timestamp FROM df")
conn.close()

print(f"Loaded {len(df)} rows across {len(metrics)} metrics with intentional anomalies.")
print("Metrics:", list(metrics.keys()))
print("Now click 'Run Pipeline Now' on the dashboard!")
