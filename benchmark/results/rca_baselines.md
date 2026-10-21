# Root-cause origin localisation vs baselines

Synthetic benchmark, 10 seeds; same detector output for every strategy.

| Strategy | Exact origins | Origin precision | Origin recall | Origin F1 | Top-5 chain precision | Time (s) |
|---|---:|---:|---:|---:|---:|---:|
| Largest deviation (top movers) | 70.0 ± 45.8% | 85.0 ± 22.9% | 85.0 ± 22.9% | 85.0 ± 22.9% | — | 0.00 ± 0.00 |
| Earliest anomaly | 0.0 ± 0.0% | 35.0 ± 22.9% | 35.0 ± 22.9% | 35.0 ± 22.9% | — | 0.00 ± 0.00 |
| Correlation graph + ranking | 30.0 ± 45.8% | 71.7 ± 29.9% | 80.0 ± 33.2% | 73.7 ± 28.8% | 30.0 ± 10.0% | 0.81 ± 1.98 |
| Granger graph + ranking | 60.0 ± 49.0% | 100.0 ± 0.0% | 80.0 ± 24.5% | 86.7 ± 16.3% | 98.0 ± 6.0% | 0.13 ± 0.02 |
| VARLiNGAM graph + ranking | 40.0 ± 49.0% | 100.0 ± 0.0% | 70.0 ± 24.5% | 80.0 ± 16.3% | 98.0 ± 6.0% | 0.51 ± 0.09 |
| KAIROS without bootstrap | 100.0 ± 0.0% | 100.0 ± 0.0% | 100.0 ± 0.0% | 100.0 ± 0.0% | 100.0 ± 0.0% | 0.35 ± 0.06 |
| KAIROS (DYNOTEARS + ranking) | 100.0 ± 0.0% | 100.0 ± 0.0% | 100.0 ± 0.0% | 100.0 ± 0.0% | 100.0 ± 0.0% | 0.95 ± 0.15 |

Reproduce: `python benchmark/rca_baselines.py --seeds 10`