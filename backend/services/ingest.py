"""Turn a file that arrived at KAIROS (upload, fast transfer) into stored metrics."""
from __future__ import annotations

import logging
import time
from pathlib import Path

from backend.agents.data_collector import DataCollectorAgent
from backend.connectors.base import to_canonical
from backend.connectors.file_connector import load_files, post_aggregate_config
from backend.models.slac import SemanticLayerAutoConstructor

logger = logging.getLogger("kairos.ingest")


def suggest_for_file(path: str) -> dict:
    sample, _ = load_files([path], {}, limit=1000)
    suggestion = SemanticLayerAutoConstructor().suggest_mapping(sample)
    suggestion["columns"] = list(map(str, sample.columns))
    suggestion["sample"] = sample.head(8).astype(str).to_dict(orient="records")
    return suggestion


def ingest_file(collector: DataCollectorAgent, path: str, source: str, mapping: dict | None = None) -> dict:
    t0 = time.perf_counter()
    notes: list[str] = []
    if not mapping:
        suggestion = suggest_for_file(path)
        mapping = suggestion.get("mapping") or {}
        notes = suggestion.get("notes", [])
        if not mapping.get("ts_col"):
            raise ValueError("SLAC could not find a timestamp column — please provide a mapping")
    df, aggregated = load_files([path], mapping)
    canonical = to_canonical(df, post_aggregate_config(mapping) if aggregated else mapping)
    result = collector.ingest_dataframe(source, canonical, bytes_received=Path(path).stat().st_size,
                                        source_type="push")
    result.update({
        "mapping": mapping, "slac_notes": notes, "aggregated_at_source": aggregated,
        "raw_rows_scanned": None if aggregated else len(df), "kpi_rows": len(canonical),
        "file_bytes": Path(path).stat().st_size, "seconds": round(time.perf_counter() - t0, 3),
    })
    logger.info("Ingested %s into '%s': %d KPI rows", path, source, len(canonical))
    return result
