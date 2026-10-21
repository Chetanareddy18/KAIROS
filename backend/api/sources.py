"""Data source management — register, test, preview (with SLAC mapping) and sync connectors."""
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.deps import get_pipeline
from backend.connectors.base import ConnectorError
from backend.connectors.registry import build_connector, describe_types
from backend.models.slac import SemanticLayerAutoConstructor

router = APIRouter()
_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class SourceIn(BaseModel):
    name:        str
    type:        str
    config:      dict = Field(default_factory=dict)
    enabled:     bool = True
    description: str = ""


class SourceTest(BaseModel):
    type:   str
    config: dict = Field(default_factory=dict)


@router.get("/connectors")
def connector_types():
    return {"types": describe_types()}


@router.get("/sources")
def list_sources(p=Depends(get_pipeline)):
    return {"sources": p.collector.list_sources()}


@router.post("/sources", status_code=201)
def create_source(body: SourceIn, p=Depends(get_pipeline)):
    if not _NAME.match(body.name):
        raise HTTPException(422, "name may only contain letters, digits, '_', '-', '.'")
    if p.collector.get_source(body.name):
        raise HTTPException(409, f"source '{body.name}' already exists")
    try:
        return p.collector.upsert_source(body.name, body.type, body.config, body.enabled, body.description)
    except ConnectorError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/sources/test")
def test_unsaved(body: SourceTest):
    """Try a configuration before saving it; returns sample rows and SLAC's suggested mapping."""
    try:
        connector = build_connector("_preview", body.type, body.config)
    except ConnectorError as e:
        raise HTTPException(422, str(e)) from e
    return _test_with_slac(connector)


@router.get("/sources/{name}")
def get_source(name: str, p=Depends(get_pipeline)):
    src = p.collector.get_source(name)
    if src is None:
        raise HTTPException(404, f"source '{name}' not found")
    return src


@router.put("/sources/{name}")
def update_source(name: str, body: SourceIn, p=Depends(get_pipeline)):
    existing = p.collector.get_source(name, mask=False)
    if existing is None:
        raise HTTPException(404, f"source '{name}' not found")
    # masked secrets coming back from the UI keep their stored value
    cfg = {k: (existing["config"].get(k) if isinstance(v, str) and "••••" in v else v)
           for k, v in body.config.items()}
    try:
        return p.collector.upsert_source(name, body.type, cfg, body.enabled, body.description,
                                         managed_by=existing["managed_by"])
    except ConnectorError as e:
        raise HTTPException(422, str(e)) from e


@router.delete("/sources/{name}")
def delete_source(name: str, purge: bool = False, p=Depends(get_pipeline)):
    if p.collector.get_source(name) is None:
        raise HTTPException(404, f"source '{name}' not found")
    p.collector.delete_source(name, purge_data=purge)
    return {"deleted": name, "purged": purge}


@router.post("/sources/{name}/test")
def test_source(name: str, p=Depends(get_pipeline)):
    try:
        connector = p.collector.connector_for(name)
    except ConnectorError as e:
        raise HTTPException(404, str(e)) from e
    return _test_with_slac(connector)


@router.post("/sources/{name}/sync")
def sync_source(name: str, full_refresh: bool = False, p=Depends(get_pipeline)):
    if p.collector.get_source(name) is None:
        raise HTTPException(404, f"source '{name}' not found")
    return p.collector.sync_source(name, full_refresh=full_refresh)


@router.post("/sources/sync-all")
def sync_all(p=Depends(get_pipeline)):
    return p.collector.collect_all()


def _test_with_slac(connector) -> dict:
    result = connector.test_connection()
    if result.get("ok") and result.get("sample"):
        try:
            sample = connector.preview(200)
            result["slac"] = SemanticLayerAutoConstructor().suggest_mapping(sample)
        except Exception as e:  # noqa: BLE001
            result["slac"] = {"mapping": {}, "notes": [f"SLAC could not inspect the sample: {e}"]}
    return result
