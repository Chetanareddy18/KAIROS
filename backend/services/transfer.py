"""KAIROS Fast Transfer — chunked, parallel, compressed, resumable, verified uploads.

Why plain FTP is slow for big files: one TCP stream (throughput capped by
window/latency), uncompressed bytes, and a dropped connection means starting
over. Fast Transfer fixes each of those:

  1. chunking      the file is split into fixed-size chunks (default 8 MB)
  2. parallelism   clients upload many chunks at once over separate streams
  3. compression   each chunk may be gzip/zstd compressed on the wire
  4. resume        GET /transfer/{id} lists missing chunks; only those are re-sent
  5. integrity     every chunk carries a SHA-256, the whole file is re-hashed on completion

The same protocol is used by the browser (dashboard "Fast Transfer" page) and by
the edge agent CLI. On completion the file can be ingested straight into KAIROS
(SLAC infers the mapping if none was given; large raw files are aggregated by
DuckDB out-of-core).
"""
from __future__ import annotations

import gzip
import hashlib
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path

from backend.config import settings
from backend.db import Database, get_db

logger = logging.getLogger("kairos.transfer")

_COMPRESSIONS = {"none", "gzip", "zstd"}


class TransferError(ValueError):
    pass


def _decompress(data: bytes, compression: str) -> bytes:
    if compression == "gzip":
        return gzip.decompress(data)
    if compression == "zstd":
        import zstandard
        return zstandard.ZstdDecompressor().decompressobj().decompress(data)
    return data


class FastTransferService:
    def __init__(self, db: Database | None = None, root: Path | None = None):
        self.db   = db or get_db()
        self.root = Path(root or settings.transfer_dir)
        self.out  = settings.upload_dir if root is None else Path(root) / "completed"
        self.root.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self._locks: dict[str, threading.Lock] = {}

    def _dir(self, tid: str) -> Path:
        if not tid.replace("-", "").isalnum():
            raise TransferError("bad transfer id")
        return self.root / tid

    def _data(self, tid: str) -> Path:
        return self._dir(tid) / "data.partial"

    def _received(self, tid: str) -> set[int]:
        log = self._dir(tid) / "received.log"
        if not log.exists():
            return set()
        return {int(x) for x in log.read_text().split() if x.strip().isdigit()}

    def _meta(self, tid: str) -> dict:
        rows = self.db.execute(
            "SELECT id, filename, size_bytes, chunk_size, total_chunks, sha256, compression, source_name, "
            "status, bytes_on_wire, created_at, completed_at, stored_path, error FROM transfers WHERE id = ?", [tid])
        if not rows:
            raise TransferError(f"unknown transfer '{tid}'")
        keys = ["id", "filename", "size_bytes", "chunk_size", "total_chunks", "sha256", "compression",
                "source_name", "status", "bytes_on_wire", "created_at", "completed_at", "stored_path", "error"]
        m = dict(zip(keys, rows[0]))
        for k in ("created_at", "completed_at"):
            m[k] = m[k].isoformat() if m[k] else None
        return m

    # ── protocol ─────────────────────────────────────────────────────────────

    def start(self, filename: str, size_bytes: int, chunk_size: int, sha256: str | None = None,
              compression: str = "none", source_name: str | None = None) -> dict:
        filename = os.path.basename(filename or "upload.bin")
        if compression not in _COMPRESSIONS:
            raise TransferError(f"compression must be one of {sorted(_COMPRESSIONS)}")
        if size_bytes < 0 or size_bytes > settings.max_upload_mb * 1024 * 1024:
            raise TransferError(f"file too large (limit {settings.max_upload_mb} MB)")
        if chunk_size < 64 * 1024 or chunk_size > 64 * 1024 * 1024:
            raise TransferError("chunk_size must be between 64 KB and 64 MB")
        total = max(1, -(-size_bytes // chunk_size))
        # resume across sessions: same file (name + size + hash) with an unfinished transfer
        if sha256:
            rows = self.db.execute(
                "SELECT id FROM transfers WHERE filename = ? AND size_bytes = ? AND sha256 = ? "
                "AND chunk_size = ? AND status IN ('uploading', 'created') ORDER BY created_at DESC LIMIT 1",
                [filename, size_bytes, sha256, chunk_size])
            if rows:
                logger.info("Resuming transfer %s for %s", rows[0][0], filename)
                return self.status(rows[0][0])
        tid = uuid.uuid4().hex
        self._dir(tid).mkdir(parents=True, exist_ok=True)
        with open(self._data(tid), "wb") as fh:          # pre-sized: chunks are written in place, no reassembly
            fh.truncate(size_bytes)
        self.db.execute(
            "INSERT INTO transfers (id, filename, size_bytes, chunk_size, total_chunks, sha256, compression, "
            "source_name, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'created')",
            [tid, filename, size_bytes, chunk_size, total, sha256, compression, source_name])
        return self.status(tid)

    def put_chunk(self, tid: str, index: int, data: bytes, chunk_sha256: str | None = None) -> dict:
        meta = self._meta(tid)
        if meta["status"] in ("completed", "failed"):
            raise TransferError(f"transfer is {meta['status']}")
        if not 0 <= index < meta["total_chunks"]:
            raise TransferError(f"chunk index {index} out of range 0..{meta['total_chunks'] - 1}")
        raw = _decompress(data, meta["compression"])
        expected_len = meta["chunk_size"] if index < meta["total_chunks"] - 1 else \
            meta["size_bytes"] - meta["chunk_size"] * (meta["total_chunks"] - 1)
        if len(raw) != expected_len:
            raise TransferError(f"chunk {index}: expected {expected_len} bytes, got {len(raw)}")
        if chunk_sha256 and hashlib.sha256(raw).hexdigest() != chunk_sha256.lower():
            raise TransferError(f"chunk {index}: checksum mismatch — please resend")
        # write in place at the chunk's offset (parallel writers touch disjoint ranges), flush to disk,
        # and only then record the chunk as received — a crash mid-write just means it is re-sent
        with open(self._data(tid), "r+b") as fh:
            fh.seek(index * meta["chunk_size"])
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        lock = self._locks.setdefault(tid, threading.Lock())
        with lock, open(self._dir(tid) / "received.log", "a") as log:
            log.write(f"{index}\n")
        self.db.execute("UPDATE transfers SET status = 'uploading', bytes_on_wire = bytes_on_wire + ? WHERE id = ?",
                        [len(data), tid])
        return {"index": index, "received": True, "wire_bytes": len(data), "raw_bytes": len(raw)}

    def status(self, tid: str) -> dict:
        meta = self._meta(tid)
        have = sorted(self._received(tid)) if self._dir(tid).exists() else []
        if meta["status"] == "completed":
            have = list(range(meta["total_chunks"]))
        missing = sorted(set(range(meta["total_chunks"])) - set(have))
        return {**meta, "received_chunks": len(have), "missing": missing[:5000],
                "progress": round(len(have) / meta["total_chunks"], 4)}

    def complete(self, tid: str) -> dict:
        lock = self._locks.setdefault(tid, threading.Lock())
        with lock:
            st = self.status(tid)
            if st["status"] == "completed":
                return st
            if st["missing"]:
                raise TransferError(f"{len(st['missing'])} chunk(s) still missing: {st['missing'][:10]}")
            d = self._dir(tid)
            target = self.out / f"{tid[:8]}_{st['filename']}"
            h = hashlib.sha256()
            with open(self._data(tid), "rb") as fh:
                while block := fh.read(4 << 20):
                    h.update(block)
            digest = h.hexdigest()
            if st["sha256"] and digest != st["sha256"].lower():
                self.db.execute("UPDATE transfers SET status = 'failed', error = ? WHERE id = ?",
                                ["file checksum mismatch", tid])
                raise TransferError("file checksum mismatch after reassembly")
            os.replace(self._data(tid), target)          # same volume: a rename, not a copy
            shutil.rmtree(d, ignore_errors=True)
            self.db.execute(
                "UPDATE transfers SET status = 'completed', completed_at = now(), stored_path = ?, sha256 = ? "
                "WHERE id = ?", [str(target), digest, tid])
            logger.info("Transfer %s complete: %s (%d bytes, %d on wire)", tid, target, st["size_bytes"],
                        st["bytes_on_wire"])
            return self.status(tid)

    def list(self, limit: int = 30) -> list[dict]:
        ids = [r[0] for r in self.db.execute("SELECT id FROM transfers ORDER BY created_at DESC LIMIT ?", [limit])]
        return [self.status(i) for i in ids]

    def abort(self, tid: str) -> None:
        shutil.rmtree(self._dir(tid), ignore_errors=True)
        self.db.execute("UPDATE transfers SET status = 'failed', error = 'aborted' WHERE id = ?", [tid])
