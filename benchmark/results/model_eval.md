# KAIROS model evaluation

Synthetic benchmark: 15 metrics from 4 sources, 336 hourly points, 12 ground-truth lagged causal edges, 2 injected incidents + 6 point anomalies. Mean ± std over 10 random seeds.

## A. Causal discovery

| Method | Precision | Recall | F1 | SHD | Edges | Time (s) |
|---|---:|---:|---:|---:|---:|---:|
| DYNOTEARS (KAIROS) | 1.00 ± 0.00 | 0.95 ± 0.04 | 0.97 ± 0.02 | 0.6 ± 0.5 | 11.4 ± 0.5 | 0.25 ± 0.09 |
| Granger (lagged OLS) | 0.83 ± 0.13 | 0.99 ± 0.03 | 0.90 ± 0.08 | 2.8 ± 2.5 | 14.6 ± 2.3 | 0.00 ± 0.00 |
| VARLiNGAM | 0.78 ± 0.11 | 0.99 ± 0.03 | 0.87 ± 0.08 | 3.7 ± 2.5 | 15.6 ± 2.2 | 0.53 ± 0.19 |
| Pearson correlation | 0.44 ± 0.01 | 0.58 ± 0.07 | 0.50 ± 0.03 | 7.0 ± 0.9 | 16.0 ± 1.8 | 0.00 ± 0.00 |

## B. Root-cause origin localisation (Agent 2 → Agent 3)

- Both incident origins reported exactly: **100%** of runs
- Origin recall 100.0 ± 0.0%, origin precision 100.0 ± 0.0%
- Investigation time 1.58 ± 0.57 s (DYNOTEARS + 2 bootstrap refits + DoWhy)

## C. Anomaly detection

| Detector | Event recall | Point precision | Flags | Time (s) | Seeds |
|---|---:|---:|---:|---:|---:|
| Robust seasonal z-score | 100.0 ± 0.0% | 77.2 ± 6.2% | 64.6 ± 6.9 | 0.23 ± 0.04 | 10 |
| Robust z + Prophet ensemble | 100.0 ± 0.0% | 75.2 ± 4.1% | 66.0 ± 6.4 | 3.34 ± 0.35 | 5 |

## D. LLM-Modulo verifier

- Faithful reports accepted: 100% (n=5)
- Corrupted numbers caught: 98.5% (n=200)
- Invented metric names caught: 100.0% (n=50)
- Faithful one-decimal rounding accepted: 100.0% (n=200)

Reproduce: `python benchmark/evaluate_models.py --seeds 10`