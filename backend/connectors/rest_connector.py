"""Generic REST/HTTP connector — Shopify, Stripe, HubSpot, Zoho, in-house APIs ...

One config-driven adapter instead of one connector per SaaS product:

    url:          https://api.example.com/v1/orders
    headers:      {Authorization: "Bearer ${SHOP_TOKEN}"}
    params:       {status: paid}
    since_param:  created_after            # incremental: only records after the watermark
    since_format: iso | epoch | epoch_ms
    records_path: data.items               # where the list of records lives in the JSON
    pagination:   {type: page, param: page, max_pages: 50}
               |  {type: cursor, param: cursor, next_path: meta.next_cursor}
               |  {type: link}             # follow `next` URL found at next_path
"""
from __future__ import annotations

import logging

import httpx
import pandas as pd

from backend.connectors.base import BaseConnector, ConnectorError, parse_since

logger = logging.getLogger("kairos.connector.rest")


def _dig(obj, path: str | None):
    if not path:
        return obj
    for part in path.split("."):
        if obj is None:
            return None
        obj = obj[int(part)] if isinstance(obj, list) and part.isdigit() else obj.get(part) if isinstance(obj, dict) else None
    return obj


class RESTConnector(BaseConnector):
    type        = "rest"
    label       = "REST API"
    description = "Config-driven HTTP JSON source with auth headers, paging and incremental `since`."
    CONFIG_FIELDS = [
        {"name": "url", "label": "Endpoint URL", "type": "text", "required": True},
        {"name": "headers", "label": "Headers (JSON)", "type": "json", "required": False,
         "help": '{"Authorization": "Bearer ${API_TOKEN}"}'},
        {"name": "params", "label": "Query params (JSON)", "type": "json", "required": False},
        {"name": "records_path", "label": "Records path", "type": "text", "required": False,
         "help": "dot path to the record list, e.g. data.items"},
        {"name": "since_param", "label": "Incremental param", "type": "text", "required": False},
    ]

    def _get_pages(self, since: pd.Timestamp | None, max_pages: int | None = None) -> tuple[list, int]:
        cfg     = self.config
        url     = cfg.get("url")
        if not url:
            raise ConnectorError("'url' is required")
        params  = dict(cfg.get("params") or {})
        if since is not None and cfg.get("since_param"):
            fmt = cfg.get("since_format", "iso")
            params[cfg["since_param"]] = (
                int(since.timestamp()) if fmt == "epoch"
                else int(since.timestamp() * 1000) if fmt == "epoch_ms"
                else since.isoformat()
            )
        pag       = cfg.get("pagination") or {"type": "none"}
        max_pages = max_pages or int(pag.get("max_pages", 100))
        records, nbytes, page = [], 0, int(pag.get("start", 1))

        with httpx.Client(timeout=float(cfg.get("timeout", 30)), headers=cfg.get("headers") or {},
                          follow_redirects=True) as client:
            for _ in range(max_pages):
                if pag.get("type") == "page":
                    params[pag.get("param", "page")] = page
                resp = client.request(cfg.get("method", "GET"), url, params=params,
                                      json=cfg.get("body") if cfg.get("method", "GET") != "GET" else None)
                resp.raise_for_status()
                nbytes += len(resp.content)
                payload = resp.json()
                batch   = _dig(payload, cfg.get("records_path"))
                if isinstance(batch, dict):
                    batch = [batch]
                batch = batch or []
                records.extend(batch)

                kind = pag.get("type", "none")
                if kind == "page":
                    if not batch:
                        break
                    page += 1
                elif kind == "cursor":
                    nxt = _dig(payload, pag.get("next_path"))
                    if not nxt:
                        break
                    params[pag.get("param", "cursor")] = nxt
                elif kind == "link":
                    nxt = _dig(payload, pag.get("next_path", "next"))
                    if not nxt:
                        break
                    url, params = nxt, {}
                else:
                    break
        return records, nbytes

    def fetch_raw(self, state: dict):
        records, nbytes = self._get_pages(parse_since(state))
        df = pd.json_normalize(records) if records else pd.DataFrame()
        return df, state, {"bytes": nbytes, "records": len(records)}

    def preview(self, limit: int = 20) -> pd.DataFrame:
        records, _ = self._get_pages(None, max_pages=1)
        return pd.json_normalize(records[:limit]) if records else pd.DataFrame()
