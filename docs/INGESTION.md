# Data ingestion strategy — "data can come from any source"

This document answers the second-evaluation review questions:

1. *Data can come from any source — how will KAIROS get it?*
2. *Different companies use different connectors, and connectors are heavy and expensive.*
3. *Can we use FTP? FTP is slow for large files.*
4. *What if the data is large?*
5. *Another student built a tool that transfers even large files directly. Can KAIROS?*

The short answer: **KAIROS moves metrics, not datasets.** It uses five lightweight
protocol-level adapters (not one connector per product), processes large data where it lives,
and has its own fast transfer for the cases where a raw file really must move.

---

## 1. The principle: move the computation, not the data

KAIROS monitors **KPI time series** (revenue per hour, orders per hour, churn rate…), not raw
transactions. 50 KPIs at 15-minute resolution is 4,800 rows a day, about 200 KB. Even a
10-million-row order table reduces to that inside the source's own database with a `GROUP BY`.
FTP and ELT are slow and expensive because teams ship **full, raw** dumps over and over. KAIROS
avoids both the "full" and the "raw".

## 2. Five protocol adapters instead of hundreds of connectors

Almost every business system exposes data through one of a few standard routes, so KAIROS
implements the routes rather than the products. Each adapter is about 100–200 lines and follows
one contract, `fetch(state) -> (df, state, stats)` (`backend/connectors/base.py`).

| Adapter | Covers | Code |
|---|---|---|
| **SQL** (any SQLAlchemy driver) | PostgreSQL, MySQL, SQL Server, Oracle, SQLite, Snowflake, BigQuery, Redshift, Databricks, and ERPs/CRMs on a DB | `sql_connector.py` |
| **SFTP / FTPS / FTP** | any system that can drop a scheduled export | `sftp_connector.py` |
| **Files & object storage** | CSV, Excel, Parquet, JSON, gz/zst; local, S3, GCS, HTTPS | `file_connector.py` |
| **REST** (config-driven) | Shopify, Stripe, HubSpot, Zoho, in-house APIs | `rest_connector.py` |
| **Push** (`POST /api/v1/ingest`) | webhooks, IoT, custom apps, the edge agent | `api/ingest.py` |
| Google Sheets | small teams' spreadsheets | `sheets_connector.py` |

A new company is onboarded with **configuration, not code**. Sources come from `sources.yaml`
or the dashboard's *Data Sources* page. **SLAC** (Semantic Layer Auto-Construction) inspects a
sample and infers the mapping automatically:

- the timestamp column
- long vs wide shape
- which columns are metrics
- whether raw records need aggregation

That mapping is the manual modelling work paid ELT and semantic-layer tools charge for.

**Cost:** ₹0. No paid connector platform, no volume-based billing (Fivetran bills by monthly
active rows; KAIROS moves only aggregated rows). Most mid-size companies already centralise data
in a warehouse, so a single read-only SQL connection is often enough. For rare systems,
open-source Airbyte or Singer can feed a database or file that KAIROS then reads.

## 3. Yes, FTP. The SFTP/FTP connector and why it stays fast

The reviewer is right that FTP is a valid, universal, zero-cost route. KAIROS keeps it fast by
design (`backend/connectors/sftp_connector.py`):

- **Only new files are fetched.** A per-source state records each file's name, size and mtime,
  so files already processed are never downloaded again (tested in
  `tests/test_connectors.py::test_ftp_fetches_only_new_files`, and live in the demo).
- **Half-written files are skipped**, using `min_age_seconds` or a `.done` marker.
- **Compressed exports** (`.csv.gz`, `.zst`, Parquet) are read directly.
- **Small KPI files, not raw dumps.** If a client can only export raw records, `aggregate`
  reduces them to KPIs as they are read.
- **Security:** use SFTP or FTPS. Plain FTP sends credentials unencrypted. Use read-only
  accounts, with passwords taken from env vars (`password_env`).

FTP is slow only for **large** files. KAIROS's FTP files are small (the demo's 15 daily logistics
files total 6 KB). When the data is large, KAIROS uses a different route (section 4).

## 4. Large data: four strategies

| Situation | KAIROS route | What travels |
|---|---|---|
| Large table in a database | **SQL push-down.** The aggregating query runs in the source DB, with `:since` for incremental loads | KPI rows (the demo turns 100k raw rows into 20 KB) |
| Large raw files on the company's servers | **Edge agent** (`edge_agent/kairos_edge.py aggregate`). DuckDB aggregates locally, out-of-core, and pushes only KPIs | KB instead of GB |
| Large files in cloud storage | **File connector on S3/GCS/HTTPS.** DuckDB reads only the needed columns and row groups of Parquet | a fraction of the file |
| The raw file itself is needed | **KAIROS Fast Transfer** (section 5) | compressed chunks, in parallel, resumable |

Also:

- **Incremental by default.** Every connector stores a watermark or state; each run moves only new data.
- **Idempotent upserts.** The primary key `(source, metric_name, timestamp)` means re-runs never duplicate rows.
- **Parallel collection.** Connectors run concurrently, each with a timeout, so one slow source never blocks the others.
- **The historical backfill happens once** (e.g. overnight through Fast Transfer or a direct query). After that, only small increments move.

## 5. KAIROS Fast Transfer: direct large-file transfer, done right

Tools that "transfer large files directly" (Aspera, Signiant, S3 multipart, rclone) all combine the
same techniques. KAIROS implements them (`backend/services/transfer.py`, client in the edge agent and in
the dashboard's *Fast Transfer* page):

1. **Chunking.** The file is split into 1–32 MB chunks.
2. **Parallel streams.** N chunks upload at once. One TCP stream is capped by window size and
   latency; several streams use the whole link.
3. **Compression.** Each chunk is compressed on the wire with gzip or zstd. CSV shrinks about 4×.
4. **Resume.** `GET /transfer/{id}` lists missing chunks. After a drop, only those are re-sent.
5. **Integrity.** Every chunk carries a SHA-256, and the server re-hashes the whole file.
6. **No reassembly copy.** Chunks are written in place into a pre-sized file and committed with a rename.

On completion the file can be ingested straight away, with a SLAC-inferred mapping. Raw records are
aggregated by DuckDB.

### Measured results

From `benchmark/benchmark_ingestion.py`; full table in `benchmark/results/results.md`.

The setup is 2,000,000 raw order rows (≈106 MB CSV). The KAIROS API runs in its own process
alongside a real FTP server. Each connection is capped at 50 Mbit/s to emulate a WAN, applied
identically to FTP and Fast Transfer:

| Method | Time | Bytes on wire | vs FTP |
|---|---:|---:|---:|
| FTP, single stream, raw CSV | 16.9 s | 105.6 MB | 1.0× |
| FTP, single stream, gzip CSV (incl. compression) | 9.2 s | 27.1 MB | 1.8× |
| **KAIROS Fast Transfer**, 8 streams, gzip | 2.8 s | 27.1 MB | **6.1×** |
| **KAIROS Fast Transfer**, 8 streams, zstd | 2.6 s | 29.4 MB | **6.4×** |
| Fast Transfer resumed after a 50% drop | 1.7 s | 13.6 MB (missing half only) | 10.2× |
| **KAIROS Edge Agent** (aggregate → push KPIs) | 1.3 s | **193 KB** | **12.6×**, ≈548× fewer bytes |

Byte counts are real. Timings vary with machine load: on a busy machine Fast Transfer measured
1.8–2.1×, because chunk compression is CPU-bound. The link is emulated on localhost, and
real-WAN measurements are future work.

## 6. Answer for the viva

> "KAIROS doesn't transfer datasets, it transfers metrics. We don't build a connector per
> product. Five lightweight protocol adapters (SQL, SFTP/FTP, files and cloud storage, REST, and a
> push endpoint) cover almost every company system, configured rather than coded, with SLAC
> inferring each new schema. Yes, we support FTP, as SFTP, and it stays fast because KAIROS fetches
> only new, small, compressed KPI files. For large data we move the computation, not the data:
> aggregation runs inside the source database, or in our edge agent next to the files, so gigabytes
> become kilobytes. When the raw file itself must move, our Fast Transfer splits it into compressed
> chunks, sends them over parallel streams, verifies every chunk with SHA-256 and resumes after a
> drop. We benchmarked it against single-stream FTP on a 2-million-row export."

## 7. Live demo script (5 minutes)

```bash
python scripts/generate_demo_sources.py      # ERP (SQLite), CSV exports, FTP drop, REST API
python scripts/demo_servers.py               # FTP :2121 + REST :8090 (separate terminal)
uvicorn backend.main:app                     # KAIROS loads sources.yaml
cd frontend && npm run dev                   # http://localhost:5173
```

1. **Data Sources → Sync all.** Four different systems ingest. Point out the "Transferred" column:
   about 20 KB from a 100k-row ERP table.
2. **Sync again.** 0 new FTP files and 0 rows: it's incremental.
3. Copy a new `logistics_*.csv.gz` into `data/demo/ftp/kpis/`, then Sync. Only that file is fetched.
4. **Fast Transfer.** Drop `data/demo/erp_orders_raw.csv.gz`, then Pause and Resume. SLAC
   suggests a mapping, click Ingest, and the benchmark chart is shown below it.
5. **Edge agent:**
   `python edge_agent/kairos_edge.py aggregate --input data/demo/erp_orders_raw.csv.gz --ts-col created_at --metric amount:revenue:sum --count-metric orders --source store_edge`.
   It prints the raw size versus what was sent.
6. **Overview → Run pipeline now**, then **Causal Analysis** (the graph shows the origin) and
   **Reports** (a verified report).
