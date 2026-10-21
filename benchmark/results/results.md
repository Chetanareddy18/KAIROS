# KAIROS ingestion benchmark

Raw export: **2,000,000 order rows, 105.6 MB** (gzip 27.1 MB). Link: 50 Mbit/s per connection (emulated WAN). Fast Transfer: 8 streams × 4 MB chunks.

| Method | Time (s) | Bytes on wire | Speed-up vs FTP | Notes |
|---|---:|---:|---:|---|
| 1. FTP single stream, raw CSV | 16.90 | 105.6 MB | 1.0× |  |
| 2. FTP single stream, gzip CSV | 9.18 | 27.1 MB | 1.8× | incl. 4.8s compression |
| 3a. KAIROS Fast Transfer (8 streams, gzip) | 2.76 | 27.1 MB | 6.1× | SHA-256 verified |
| 3b. KAIROS Fast Transfer (8 streams, zstd) | 2.63 | 29.4 MB | 6.4× | SHA-256 verified, faster codec |
| 4. Fast Transfer, resumed after 50% drop | 1.65 | 13.6 MB | 10.2× | re-sent 14/27 chunks only (first half: 0.905s) |
| 5. KAIROS Edge Agent (aggregate → push KPIs) | 1.34 | 192.7 KB | 12.6× | 2,000,000 rows → 2,160 KPI records |

Reproduce: `python benchmark/benchmark_ingestion.py --rows 2000000 --stream-mbps 50`