"""KAIROS Fast Transfer: chunking, compression, resume, integrity."""
import gzip
import hashlib
import os

import pytest

from backend.services.transfer import FastTransferService, TransferError

CHUNK = 256 * 1024


@pytest.fixture
def svc(db, tmp_path):
    return FastTransferService(db, root=tmp_path / "transfers")


def _chunks(data: bytes):
    return [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]


def test_parallel_out_of_order_gzip_upload(svc):
    data = os.urandom(CHUNK * 3) + b"tail" * 1000
    st = svc.start("big.bin", len(data), CHUNK, hashlib.sha256(data).hexdigest(), "gzip")
    parts = _chunks(data)
    for i in reversed(range(len(parts))):                    # any order, as parallel streams arrive
        svc.put_chunk(st["id"], i, gzip.compress(parts[i]), hashlib.sha256(parts[i]).hexdigest())
    done = svc.complete(st["id"])
    assert done["status"] == "completed"
    with open(done["stored_path"], "rb") as fh:
        assert fh.read() == data


def test_resume_after_interruption(svc):
    data = os.urandom(CHUNK * 4)
    sha = hashlib.sha256(data).hexdigest()
    st = svc.start("r.bin", len(data), CHUNK, sha)
    parts = _chunks(data)
    svc.put_chunk(st["id"], 0, parts[0])
    svc.put_chunk(st["id"], 2, parts[2])
    # "connection drops" — client restarts and asks what is missing
    again = svc.start("r.bin", len(data), CHUNK, sha)
    assert again["id"] == st["id"] and again["missing"] == [1, 3]
    for i in again["missing"]:
        svc.put_chunk(st["id"], i, parts[i])
    assert svc.complete(st["id"])["status"] == "completed"


def test_corrupt_chunk_rejected(svc):
    data = os.urandom(CHUNK * 2)
    st = svc.start("c.bin", len(data), CHUNK, hashlib.sha256(data).hexdigest())
    part = _chunks(data)[0]
    with pytest.raises(TransferError, match="checksum"):
        svc.put_chunk(st["id"], 0, part[:-1] + b"X", hashlib.sha256(part).hexdigest())
    with pytest.raises(TransferError, match="missing"):
        svc.complete(st["id"])


def test_whole_file_hash_mismatch_fails(svc):
    data = os.urandom(CHUNK)
    st = svc.start("h.bin", len(data), CHUNK, "0" * 64)
    svc.put_chunk(st["id"], 0, data)
    with pytest.raises(TransferError, match="mismatch"):
        svc.complete(st["id"])


def test_zstd_compression(svc):
    import zstandard
    data = b"timestamp,metric,value\n" + b"2026-01-01,a,1\n" * 50_000
    st = svc.start("z.csv", len(data), 512 * 1024, hashlib.sha256(data).hexdigest(), "zstd")
    wire = 0
    for i, part in enumerate([data[j:j + 512 * 1024] for j in range(0, len(data), 512 * 1024)]):
        payload = zstandard.ZstdCompressor().compress(part)
        wire += len(payload)
        svc.put_chunk(st["id"], i, payload)
    assert svc.complete(st["id"])["status"] == "completed"
    assert wire < len(data) / 10                                 # repetitive CSV compresses >10x
