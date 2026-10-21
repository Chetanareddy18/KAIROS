#!/usr/bin/env python3
"""KAIROS Edge Agent — runs inside the company's network, next to the data.

Two ways to get large data into KAIROS without slow bulk transfers:

  aggregate   "Move the computation, not the data." Reads a large raw file locally
              with DuckDB (streaming, out-of-core), computes KPIs per time bucket and
              pushes only those to KAIROS. A multi-GB export becomes a few KB.
              Incremental: remembers the last bucket it sent.

  transfer    When the raw file itself is needed: KAIROS Fast Transfer — the file is
              split into chunks, each chunk compressed (gzip/zstd), hashed (SHA-256)
              and uploaded over N parallel streams with retries; an interrupted
              upload resumes from the missing chunks only.

Examples
  python kairos_edge.py aggregate --input orders_2026.csv.gz --ts-col created_at \\
      --metric amount:revenue:sum --metric items:units_sold:sum --count-metric orders \\
      --freq 1h --source store_42 --server https://kairos.example.com --api-key $KAIROS_API_KEY

  python kairos_edge.py transfer --file warehouse_dump.parquet --workers 8 --compress zstd \\
      --server http://localhost:8000 --ingest --source warehouse

Dependencies: httpx (always), duckdb (aggregate), zstandard (optional, for --compress zstd).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

# 127.0.0.1 rather than localhost: on Windows "localhost" tries IPv6 first and stalls ~2 s per connection
DEFAULT_SERVER = os.getenv("KAIROS_SERVER", "http://127.0.0.1:8000")
_AGG = {"sum": "sum", "mean": "avg", "avg": "avg", "min": "min", "max": "max", "count": "count",
        "median": "median", "last": "last", "first": "first"}


def _headers(api_key: str | None) -> dict:
    return {"X-API-Key": api_key} if api_key else {}


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


class Throttle:
    """Optional per-stream bandwidth cap — used by the benchmark to emulate a WAN link."""

    def __init__(self, mbps: float = 0.0):
        self.bps = mbps * 1024 * 1024 / 8 if mbps else 0.0

    def wait(self, nbytes: int, started: float) -> None:
        if self.bps:
            target = nbytes / self.bps
            elapsed = time.perf_counter() - started
            if target > elapsed:
                time.sleep(target - elapsed)


# ── aggregate ────────────────────────────────────────────────────────────────

def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def aggregate_file(path: str, ts_col: str, metrics: list[tuple[str, str, str]], count_metric: str | None,
                   freq: str = "1h", since: str | None = None) -> tuple[list[dict], dict]:
    """Aggregate a raw file into KPI records with DuckDB. metrics: [(column, metric_name, agg)]."""
    import duckdb

    n, unit = int("".join(c for c in freq if c.isdigit()) or 1), "".join(c for c in freq if c.isalpha()).lower()
    unit = {"min": "minutes", "m": "minutes", "h": "hours", "d": "days", "s": "seconds"}.get(unit, "hours")
    lower = path.lower()
    path = path.replace("'", "''")
    reader = (f"read_parquet('{path}')" if lower.endswith((".parquet", ".pq"))
              else f"read_json_auto('{path}')" if ".json" in lower
              else f"read_csv_auto('{path}', sample_size = 20000)")
    bucket = f"time_bucket(INTERVAL '{n} {unit}', TRY_CAST({_q(ts_col)} AS TIMESTAMPTZ))"
    selects = [f"{bucket} AS ts"]
    for col, name, agg in metrics:
        selects.append(f"{_AGG[agg]}(TRY_CAST({_q(col)} AS DOUBLE)) AS {_q(name)}")
    if count_metric:
        selects.append(f"count(*) AS {_q(count_metric)}")
    selects.append("count(*) AS __raw_rows")          # single pass: row count comes from the same scan
    where = f"WHERE TRY_CAST({_q(ts_col)} AS TIMESTAMPTZ) >= TIMESTAMPTZ '{since}'" if since else ""
    con = duckdb.connect()
    con.execute("SET TimeZone = 'UTC'")
    t0 = time.perf_counter()
    rows = con.execute(f"SELECT {', '.join(selects)} FROM {reader} {where} GROUP BY 1 HAVING ts IS NOT NULL "
                       f"ORDER BY 1").fetchall()
    cols = ["ts"] + [m[1] for m in metrics] + ([count_metric] if count_metric else [])
    raw_rows = sum(r[-1] for r in rows)
    records = []
    for r in rows:
        ts = r[0].isoformat()
        for name, val in zip(cols[1:], r[1:-1]):
            if val is not None:
                records.append({"metric_name": name, "value": float(val), "timestamp": ts})
    stats = {"raw_rows": raw_rows, "file_bytes": os.path.getsize(path), "kpi_records": len(records),
             "buckets": len(rows), "aggregate_seconds": round(time.perf_counter() - t0, 3)}
    return records, stats


def push_records(server: str, source: str, records: list[dict], api_key: str | None = None,
                 batch: int = 50_000) -> dict:
    sent, payload_bytes, t0 = 0, 0, time.perf_counter()
    with httpx.Client(timeout=120, headers=_headers(api_key)) as client:
        for i in range(0, len(records), batch):
            body = json.dumps({"source": source, "records": records[i:i + batch]}).encode()
            payload_bytes += len(body)
            r = client.post(f"{server}/api/v1/ingest", content=body, headers={"Content-Type": "application/json"})
            r.raise_for_status()
            sent += r.json().get("rows", 0)
    return {"rows_stored": sent, "payload_bytes": payload_bytes, "push_seconds": round(time.perf_counter() - t0, 3)}


def cmd_aggregate(a: argparse.Namespace) -> int:
    metrics = []
    for spec in a.metric or []:
        parts = spec.split(":")
        col = parts[0]
        name = parts[1] if len(parts) > 1 and parts[1] else col
        agg = parts[2] if len(parts) > 2 else "sum"
        if agg not in _AGG:
            print(f"unknown aggregate '{agg}'", file=sys.stderr)
            return 2
        metrics.append((col, name, agg))
    if not metrics and not a.count_metric:
        print("give at least one --metric col[:name[:agg]] or --count-metric", file=sys.stderr)
        return 2
    state_path = Path(a.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    key = f"{a.source}|{Path(a.input).resolve()}"
    since = None if a.full else state.get(key)
    records, stats = aggregate_file(a.input, a.ts_col, metrics, a.count_metric, a.freq, since)
    print(f"scanned {stats['raw_rows']:,} raw rows ({_human(stats['file_bytes'])}) in {stats['aggregate_seconds']}s "
          f"-> {stats['kpi_records']:,} KPI records in {stats['buckets']:,} buckets")
    if a.dry_run or not records:
        print(json.dumps(records[:5], indent=2))
        return 0
    pushed = push_records(a.server, a.source, records, a.api_key)
    ratio = stats["file_bytes"] / max(1, pushed["payload_bytes"])
    print(f"pushed {pushed['rows_stored']:,} rows, {_human(pushed['payload_bytes'])} over the network "
          f"({ratio:,.0f}x smaller than the raw file) in {pushed['push_seconds']}s")
    state[key] = max(r["timestamp"] for r in records)   # next run re-sends the last (partial) bucket only
    state_path.write_text(json.dumps(state, indent=2))
    return 0


# ── transfer ─────────────────────────────────────────────────────────────────

def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(4 << 20):
            h.update(block)
    return h.hexdigest()


def _compress(data: bytes, method: str) -> bytes:
    if method == "gzip":
        return gzip.compress(data, compresslevel=5)
    if method == "zstd":
        import zstandard
        return zstandard.ZstdCompressor(level=3).compress(data)
    return data


def fast_transfer(path: str, server: str = DEFAULT_SERVER, workers: int = 8, chunk_mb: float = 8,
                  compress: str = "gzip", source: str | None = None, ingest: bool = False,
                  mapping: dict | None = None, api_key: str | None = None, stream_mbps: float = 0.0,
                  stop_after_chunks: int | None = None, quiet: bool = False) -> dict:
    """Upload a file with KAIROS Fast Transfer. Returns the server's completion payload plus client stats."""
    size = os.path.getsize(path)
    chunk = int(chunk_mb * 1024 * 1024)
    t0 = time.perf_counter()
    digest = sha256_file(path)
    hash_s = time.perf_counter() - t0
    with httpx.Client(timeout=300, headers=_headers(api_key),
                      limits=httpx.Limits(max_connections=workers + 2)) as client:
        st = client.post(f"{server}/api/v1/transfer/start", json={
            "filename": os.path.basename(path), "size_bytes": size, "chunk_size": chunk,
            "sha256": digest, "compression": compress, "source_name": source}).raise_for_status().json()
        tid, missing = st["id"], st["missing"]
        if not quiet and st["received_chunks"]:
            print(f"resuming transfer {tid[:8]}: {st['received_chunks']}/{st['total_chunks']} chunks already on server")
        if stop_after_chunks is not None:
            missing = missing[:stop_after_chunks]
        wire = 0
        done = 0
        lock = threading.Lock()
        throttle = Throttle(stream_mbps)

        def send(i: int) -> int:
            with open(path, "rb") as fh:
                fh.seek(i * chunk)
                raw = fh.read(chunk)
            payload = _compress(raw, compress)
            headers = {"X-Chunk-SHA256": hashlib.sha256(raw).hexdigest(),
                       "Content-Type": "application/octet-stream"}
            for attempt in range(5):
                try:
                    started = time.perf_counter()
                    r = client.put(f"{server}/api/v1/transfer/{tid}/chunk/{i}", content=payload, headers=headers)
                    r.raise_for_status()
                    throttle.wait(len(payload), started)
                    return len(payload)
                except httpx.HTTPError:
                    if attempt == 4:
                        raise
                    time.sleep(0.5 * 2 ** attempt)        # exponential backoff, then retry this chunk only
            return 0

        up0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for fut in as_completed([pool.submit(send, i) for i in missing]):
                n = fut.result()
                with lock:
                    wire += n
                    done += 1
                    if not quiet and (done % max(1, len(missing) // 20) == 0 or done == len(missing)):
                        elapsed = time.perf_counter() - up0
                        print(f"\r  {done}/{len(missing)} chunks · {_human(wire)} on wire · "
                              f"{_human(wire / max(elapsed, 1e-6))}/s", end="", flush=True)
        upload_s = time.perf_counter() - up0
        if not quiet:
            print()
        if stop_after_chunks is not None:
            return {"id": tid, "partial": True, "wire_bytes": wire, "upload_seconds": round(upload_s, 3)}
        res = client.post(f"{server}/api/v1/transfer/{tid}/complete",
                          json={"ingest": ingest, "source": source, "mapping": mapping}).raise_for_status().json()
    res["client"] = {"file_bytes": size, "wire_bytes": wire, "hash_seconds": round(hash_s, 3),
                     "upload_seconds": round(upload_s, 3), "total_seconds": round(time.perf_counter() - t0, 3),
                     "chunks_sent": len(missing), "workers": workers, "compression": compress}
    return res


def cmd_transfer(a: argparse.Namespace) -> int:
    mapping = json.loads(a.mapping) if a.mapping else None
    res = fast_transfer(a.file, a.server, a.workers, a.chunk_mb, a.compress, a.source, a.ingest, mapping, a.api_key)
    c = res["client"]
    print(f"done: {_human(c['file_bytes'])} file, {_human(c['wire_bytes'])} on the wire "
          f"({c['file_bytes'] / max(1, c['wire_bytes']):.1f}x compression), {c['total_seconds']}s total, "
          f"{_human(c['file_bytes'] / max(c['upload_seconds'], 1e-6))}/s effective")
    print(f"server verified SHA-256 {res['sha256'][:16]}… stored as {res['file_id']}")
    if res.get("ingest"):
        print("ingest:", json.dumps(res["ingest"], default=str)[:400])
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="KAIROS Edge Agent")
    p.add_argument("--server", default=DEFAULT_SERVER)
    p.add_argument("--api-key", default=os.getenv("KAIROS_API_KEY"))
    sub = p.add_subparsers(dest="cmd", required=True)

    ag = sub.add_parser("aggregate", help="aggregate a large raw file locally, push only KPIs")
    ag.add_argument("--input", required=True)
    ag.add_argument("--ts-col", required=True)
    ag.add_argument("--metric", action="append", help="column[:metric_name[:agg]]  (agg: sum|mean|min|max|...)")
    ag.add_argument("--count-metric", help="also emit the row count per bucket under this name")
    ag.add_argument("--freq", default="1h")
    ag.add_argument("--source", required=True)
    ag.add_argument("--state", default=".kairos_edge_state.json")
    ag.add_argument("--full", action="store_true", help="ignore saved state, resend everything")
    ag.add_argument("--dry-run", action="store_true")
    ag.set_defaults(func=cmd_aggregate)

    tr = sub.add_parser("transfer", help="fast chunked/parallel/compressed/resumable upload")
    tr.add_argument("--file", required=True)
    tr.add_argument("--workers", type=int, default=8)
    tr.add_argument("--chunk-mb", type=float, default=8)
    tr.add_argument("--compress", choices=["gzip", "zstd", "none"], default="gzip")
    tr.add_argument("--source")
    tr.add_argument("--ingest", action="store_true", help="ingest into KAIROS after upload")
    tr.add_argument("--mapping", help="JSON mapping (else SLAC infers it)")
    tr.set_defaults(func=cmd_transfer)

    a = p.parse_args(argv)
    for attr in ("server",):
        setattr(a, attr, getattr(a, attr).rstrip("/"))
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
