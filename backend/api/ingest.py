"""Push ingestion (webhooks / edge agent), file uploads and KAIROS Fast Transfer."""
import json
import os
import uuid
from pathlib import Path

import aiofiles
import pandas as pd
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from backend.api.deps import get_pipeline
from backend.config import settings
from backend.connectors.base import ConnectorError
from backend.services.ingest import ingest_file, suggest_for_file
from backend.services.transfer import FastTransferService, TransferError

router = APIRouter()
_transfer: FastTransferService | None = None


def transfers(p=Depends(get_pipeline)) -> FastTransferService:
    global _transfer
    if _transfer is None:
        _transfer = FastTransferService(p.db)
    return _transfer


# ── Push / webhook ────────────────────────────────────────────────────────────

class IngestBody(BaseModel):
    source:  str
    records: list[dict] = Field(default_factory=list,
                                description="[{metric_name, value, timestamp}] or raw rows + mapping")
    mapping: dict | None = None


@router.post("/ingest")
def ingest(body: IngestBody, p=Depends(get_pipeline)):
    """Webhook / edge-agent endpoint: the source pushes data, no connector needed on our side."""
    if not body.records:
        raise HTTPException(422, "records is empty")
    if len(body.records) > 200_000:
        raise HTTPException(413, "too many records in one request — batch them (max 200k)")
    df = pd.DataFrame(body.records)
    try:
        nbytes = len(json.dumps(body.records[:1000], default=str)) * max(1, len(body.records) // 1000)
        return p.collector.ingest_dataframe(body.source, df, body.mapping, bytes_received=nbytes)
    except (ConnectorError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


# ── Simple uploads (small/medium files) ───────────────────────────────────────

def _file_path(file_id: str) -> Path:
    name = os.path.basename(file_id)
    path = settings.upload_dir / name
    if not path.exists():
        raise HTTPException(404, f"file '{file_id}' not found")
    return path


@router.post("/files")
async def upload_file(file: UploadFile = File(...)):
    """Stream an upload to disk and return SLAC's suggested mapping (nothing is ingested yet)."""
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    file_id = f"{uuid.uuid4().hex[:8]}_{os.path.basename(file.filename or 'upload.csv')}"
    target = settings.upload_dir / file_id
    size, limit = 0, settings.max_upload_mb * 1024 * 1024
    async with aiofiles.open(target, "wb") as out:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > limit:
                await out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB — use Fast Transfer")
            await out.write(chunk)
    try:
        suggestion = await run_in_threadpool(suggest_for_file, str(target))
    except Exception as e:  # noqa: BLE001
        suggestion = {"mapping": {}, "notes": [f"could not read file: {e}"]}
    return {"file_id": file_id, "size_bytes": size, "suggestion": suggestion}


class FileIngestBody(BaseModel):
    source:  str
    mapping: dict | None = None


@router.post("/files/{file_id}/ingest")
def ingest_uploaded(file_id: str, body: FileIngestBody, p=Depends(get_pipeline)):
    try:
        return ingest_file(p.collector, str(_file_path(file_id)), body.source, body.mapping)
    except (ConnectorError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


@router.get("/files/{file_id}/suggest")
def suggest_uploaded(file_id: str):
    """SLAC mapping suggestion for a stored file (e.g. one that arrived via Fast Transfer)."""
    try:
        return suggest_for_file(str(_file_path(file_id)))
    except (ConnectorError, ValueError) as e:
        raise HTTPException(422, str(e)) from e


@router.get("/files")
def list_files():
    d = settings.upload_dir
    if not d.exists():
        return {"files": []}
    files = sorted(d.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True)[:50]
    return {"files": [{"file_id": f.name, "size_bytes": f.stat().st_size} for f in files if f.is_file()]}


# ── Fast Transfer (large files) ───────────────────────────────────────────────

class TransferStart(BaseModel):
    filename:    str
    size_bytes:  int
    chunk_size:  int = 8 * 1024 * 1024
    sha256:      str | None = None
    compression: str = "none"
    source_name: str | None = None


class TransferComplete(BaseModel):
    ingest:  bool = False
    source:  str | None = None
    mapping: dict | None = None


@router.post("/transfer/start")
def transfer_start(body: TransferStart, svc: FastTransferService = Depends(transfers)):
    try:
        return svc.start(body.filename, body.size_bytes, body.chunk_size, body.sha256,
                         body.compression, body.source_name)
    except TransferError as e:
        raise HTTPException(422, str(e)) from e


@router.put("/transfer/{tid}/chunk/{index}")
async def transfer_chunk(tid: str, index: int, request: Request,
                         x_chunk_sha256: str | None = Header(default=None),
                         svc: FastTransferService = Depends(transfers)):
    data = await request.body()
    try:
        return await run_in_threadpool(svc.put_chunk, tid, index, data, x_chunk_sha256)
    except TransferError as e:
        raise HTTPException(409 if "checksum" in str(e) else 422, str(e)) from e
    except OSError as e:          # corrupt compressed payload
        raise HTTPException(422, f"chunk {index}: could not decompress ({e})") from e


@router.get("/transfer/{tid}")
def transfer_status(tid: str, svc: FastTransferService = Depends(transfers)):
    try:
        return svc.status(tid)
    except TransferError as e:
        raise HTTPException(404, str(e)) from e


@router.post("/transfer/{tid}/complete")
def transfer_complete(tid: str, body: TransferComplete, svc: FastTransferService = Depends(transfers),
                      p=Depends(get_pipeline)):
    try:
        st = svc.complete(tid)
    except TransferError as e:
        raise HTTPException(409, str(e)) from e
    out = {**st, "file_id": Path(st["stored_path"]).name}
    if body.ingest:
        source = body.source or st.get("source_name") or Path(st["filename"]).stem
        try:
            out["ingest"] = ingest_file(p.collector, st["stored_path"], source, body.mapping)
        except (ConnectorError, ValueError) as e:
            out["ingest"] = {"error": str(e)}
    return out


@router.get("/transfers")
def transfer_list(svc: FastTransferService = Depends(transfers)):
    return {"transfers": svc.list()}


@router.delete("/transfer/{tid}")
def transfer_abort(tid: str, svc: FastTransferService = Depends(transfers)):
    svc.abort(tid)
    return {"aborted": tid}
