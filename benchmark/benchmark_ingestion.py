"""Ingestion benchmark — answers "how does KAIROS handle large data?" with measured numbers.

Starts a real KAIROS API (temp database) and a real FTP server on localhost, writes a
large raw transaction export, then compares:

  1. FTP, single stream, raw file           (the baseline the reviewers asked about)
  2. FTP, single stream, gzip-compressed file
  3. KAIROS Fast Transfer (8 parallel streams, gzip or zstd per chunk, SHA-256 verified)
  4. Fast Transfer interrupted at ~50% and resumed (only missing chunks re-sent)
  5. KAIROS Edge Agent: aggregate locally, push only KPIs

On localhost the network is effectively unlimited, which hides the real cost of a
single TCP stream. `--stream-mbps` caps the throughput of *each* connection to emulate
a WAN link (per-connection throughput is bounded by TCP window / round-trip time, which
is exactly why one FTP stream is slow and parallel streams help). The cap is applied
identically to FTP and Fast Transfer streams. Byte counts are always real.

    python benchmark/benchmark_ingestion.py --rows 1000000 --stream-mbps 50
"""
from __future__ import annotations

import argparse
import ftplib
import gzip
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "edge_agent"))

TMP = Path(tempfile.mkdtemp(prefix="kairos_bench_"))
os.environ.update({
    "KAIROS_ENV": "benchmark", "KAIROS_DATA_DIR": str(TMP / "data"), "KAIROS_DB_PATH": str(TMP / "bench.duckdb"),
    "KAIROS_SOURCES_FILE": str(TMP / "none.yaml"), "KAIROS_SCHEDULER_ENABLED": "false",
    "KAIROS_LLM_ENABLED": "false", "KAIROS_API_KEY": "", "TELEGRAM_BOT_TOKEN": "", "GMAIL_USER": "",
    "KAIROS_MAX_UPLOAD_MB": "20000",
})


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def start_api() -> str:
    """Run the KAIROS API in its own process, as in a real deployment (client and server never share a CPU lock)."""
    import subprocess

    import httpx
    port = free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port),
         "--log-level", "warning"],
        cwd=str(ROOT), env=os.environ.copy(),
    )
    import atexit
    atexit.register(proc.kill)
    for _ in range(600):
        try:
            if httpx.get(f"http://127.0.0.1:{port}/health", timeout=1).status_code == 200:
                return f"http://127.0.0.1:{port}"
        except httpx.HTTPError:
            time.sleep(0.25)
    proc.kill()
    raise RuntimeError("API did not start")


def start_ftp(root: Path) -> int:
    from pyftpdlib.authorizers import DummyAuthorizer
    from pyftpdlib.handlers import FTPHandler
    from pyftpdlib.servers import FTPServer
    auth = DummyAuthorizer()
    auth.add_user("bench", "bench", str(root), perm="elradfmw")
    handler = type("H", (FTPHandler,), {"authorizer": auth, "banner": "kairos bench"})
    port = free_port()
    srv = FTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=srv.serve_forever, kwargs={"timeout": 0.5}, daemon=True).start()
    return port


def ftp_upload(port: int, path: Path, stream_mbps: float) -> float:
    from kairos_edge import Throttle
    throttle = Throttle(stream_mbps)
    sent = [0]
    t0 = time.perf_counter()

    def cb(block):
        sent[0] += len(block)
        throttle.wait(sent[0], t0)

    with ftplib.FTP() as ftp:
        ftp.connect("127.0.0.1", port)
        ftp.login("bench", "bench")
        with open(path, "rb") as fh:
            ftp.storbinary(f"STOR {path.name}", fh, blocksize=256 * 1024, callback=cb)
    return time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=1_000_000)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--stream-mbps", type=float, default=50.0, help="per-connection cap (0 = unlimited)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--chunk-mb", type=float, default=4)
    ap.add_argument("--out", default=str(ROOT / "benchmark" / "results"))
    a = ap.parse_args()
    import logging
    logging.basicConfig(level=logging.WARNING, force=True)
    for name in ("pyftpdlib", "httpx", "kairos", "uvicorn"):
        logging.getLogger(name).setLevel(logging.WARNING)

    from backend.demo.synthetic import generate_transactions
    from kairos_edge import aggregate_file, fast_transfer, push_records

    print(f"generating {a.rows:,} raw order rows …")
    raw = TMP / "orders_raw.csv"
    generate_transactions(a.rows, days=a.days).to_csv(raw, index=False)
    raw_size = raw.stat().st_size
    gz = TMP / "orders_raw.csv.gz"
    t0 = time.perf_counter()
    with open(raw, "rb") as src, gzip.open(gz, "wb", compresslevel=5) as dst:
        shutil.copyfileobj(src, dst, 4 << 20)
    gzip_s = time.perf_counter() - t0
    print(f"raw export: {human(raw_size)} · gzip: {human(gz.stat().st_size)}")

    api = start_api()
    ftp_root = TMP / "ftp"
    ftp_root.mkdir()
    ftp_port = start_ftp(ftp_root)
    results = []

    def add(name, seconds, wire, note=""):
        results.append({"method": name, "seconds": round(seconds, 2), "bytes_on_wire": wire,
                        "speedup_vs_ftp": None, "note": note})
        print(f"  {name:<46} {seconds:8.2f}s  {human(wire):>12}  {note}")

    print("\nrunning …")
    add("1. FTP single stream, raw CSV", ftp_upload(ftp_port, raw, a.stream_mbps), raw_size)
    add("2. FTP single stream, gzip CSV", gzip_s + ftp_upload(ftp_port, gz, a.stream_mbps), gz.stat().st_size,
        f"incl. {gzip_s:.1f}s compression")

    res = fast_transfer(str(raw), api, workers=a.workers, chunk_mb=a.chunk_mb, compress="gzip",
                        stream_mbps=a.stream_mbps, quiet=True)
    c = res["client"]
    add(f"3a. KAIROS Fast Transfer ({a.workers} streams, gzip)", c["total_seconds"], c["wire_bytes"],
        "SHA-256 verified")
    raw_z = TMP / "orders_raw_zstd.csv"
    shutil.copy(raw, raw_z)
    cz = fast_transfer(str(raw_z), api, workers=a.workers, chunk_mb=a.chunk_mb, compress="zstd",
                       stream_mbps=a.stream_mbps, quiet=True)["client"]
    add(f"3b. KAIROS Fast Transfer ({a.workers} streams, zstd)", cz["total_seconds"], cz["wire_bytes"],
        "SHA-256 verified, faster codec")

    # interrupted + resumed: send ~half the chunks, "drop the connection", then resume
    raw2 = TMP / "orders_raw_copy.csv"
    shutil.copy(raw, raw2)
    total_chunks = -(-raw_size // int(a.chunk_mb * 1024 * 1024))
    part = fast_transfer(str(raw2), api, workers=a.workers, chunk_mb=a.chunk_mb, compress="gzip",
                         stream_mbps=a.stream_mbps, stop_after_chunks=total_chunks // 2, quiet=True)
    resumed = fast_transfer(str(raw2), api, workers=a.workers, chunk_mb=a.chunk_mb, compress="gzip",
                            stream_mbps=a.stream_mbps, quiet=True)
    rc = resumed["client"]
    add("4. Fast Transfer, resumed after 50% drop", rc["total_seconds"], rc["wire_bytes"],
        f"re-sent {rc['chunks_sent']}/{total_chunks} chunks only (first half: {part['upload_seconds']}s)")

    t0 = time.perf_counter()
    records, stats = aggregate_file(str(raw), "created_at", [("amount", "revenue", "sum"),
                                                            ("items", "units_sold", "sum")], "orders", "1h")
    pushed = push_records(api, "edge_store", records)
    add("5. KAIROS Edge Agent (aggregate → push KPIs)", time.perf_counter() - t0, pushed["payload_bytes"],
        f"{stats['raw_rows']:,} rows → {stats['kpi_records']:,} KPI records")

    base = results[0]["seconds"]
    for r in results:
        r["speedup_vs_ftp"] = round(base / r["seconds"], 1) if r["seconds"] else None

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"rows": a.rows, "raw_bytes": raw_size, "gzip_bytes": gz.stat().st_size,
            "stream_mbps_cap": a.stream_mbps, "workers": a.workers, "chunk_mb": a.chunk_mb,
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
    (out / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2))
    cap = f"{a.stream_mbps:g} Mbit/s per connection (emulated WAN)" if a.stream_mbps else "unlimited (localhost)"
    lines = [
        "# KAIROS ingestion benchmark", "",
        f"Raw export: **{a.rows:,} order rows, {human(raw_size)}** (gzip {human(gz.stat().st_size)}). "
        f"Link: {cap}. Fast Transfer: {a.workers} streams × {a.chunk_mb:g} MB chunks.", "",
        "| Method | Time (s) | Bytes on wire | Speed-up vs FTP | Notes |", "|---|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(f"| {r['method']} | {r['seconds']:.2f} | {human(r['bytes_on_wire'])} | "
                     f"{r['speedup_vs_ftp']}× | {r['note']} |")
    lines += ["", "Reproduce: `python benchmark/benchmark_ingestion.py "
              f"--rows {a.rows} --stream-mbps {a.stream_mbps:g}`"]
    (out / "results.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nresults written to {out / 'results.md'}")
    print("\n".join(lines))
    sys.stdout.flush()
    import subprocess  # noqa: F401  (atexit kills the API process)
    sys.exit(0)     # uvicorn/ftp threads are daemons; skip their slow shutdown


if __name__ == "__main__":
    main()
