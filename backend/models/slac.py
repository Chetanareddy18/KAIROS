"""SLAC — Semantic Layer Auto-Construction.

Given a raw table from any source, SLAC infers
  1. the *mapping* KAIROS needs (timestamp column, long vs wide shape, which
     columns are metrics) — so a new source works without hand-written config;
  2. the *business meaning* of each metric (unit, category, KPI or not, and
     whether "up" is good or bad) — used by the reporter to phrase alerts.

The LLM (Groq, then local Ollama) is asked for semantics; a deterministic
heuristic is always computed first and is used whenever the LLM is unavailable
or returns something that does not validate.
"""
from __future__ import annotations

import json
import logging
import re

import pandas as pd

from backend.config import settings

logger = logging.getLogger("kairos.model.slac")

_PROMPT = """
You are a business intelligence expert. Given the metric columns below (with sample values),
infer the business meaning of each.

Columns:
{schema}

Respond with JSON only, no prose:
{{
  "metrics": [
    {{
      "column": "column_name",
      "business_meaning": "plain English description",
      "unit": "currency|count|percentage|ratio|duration|score",
      "category": "revenue|cost|volume|quality|engagement|operations|unknown",
      "is_kpi": true,
      "higher_is_better": true
    }}
  ]
}}
""".strip()

# order matters: first category that matches wins
_CATEGORIES = [
    ("revenue",    {"revenue", "sales", "gmv", "mrr", "arr", "income", "turnover", "order value", "aov"}),
    ("cost",       {"cost", "expense", "spend", "cogs", "opex", "capex", "refund"}),
    ("quality",    {"nps", "csat", "rating", "satisfaction", "defect", "return", "churn", "margin"}),
    ("engagement", {"click", "ctr", "conversion", "abandon", "visit", "session", "bounce", "signup"}),
    ("operations", {"delay", "delivery", "inventory", "ticket", "response", "latency", "uptime", "stock"}),
    ("volume",     {"orders", "order count", "transactions", "units", "count", "qty", "quantity"}),
]
_LOWER_IS_BETTER = {"cost", "expense", "spend", "churn", "abandon", "delay", "ticket", "response time",
                    "refund", "defect", "return", "bounce", "latency", "cogs"}
_TS_HINTS = ("timestamp", "time", "date", "datetime", "ts", "created", "updated", "period", "day", "hour")


class SemanticLayerAutoConstructor:
    def __init__(self):
        self.groq_key = settings.groq_api_key

    # ── mapping inference ────────────────────────────────────────────────────

    def suggest_mapping(self, df: pd.DataFrame) -> dict:
        """Infer the connector mapping for a raw sample frame."""
        if df is None or df.empty:
            return {"mapping": {}, "confidence": 0.0, "notes": ["empty sample"]}
        notes: list[str] = []
        ts_col = self._find_timestamp(df)
        if ts_col is None:
            return {"mapping": {}, "confidence": 0.0, "notes": ["no timestamp-like column found"]}

        numeric = [c for c in df.columns if c != ts_col and self._is_numeric(df[c]) and not self._is_identifier(c, df[c])]
        text    = [c for c in df.columns if c != ts_col and c not in numeric]

        # long format: a low-cardinality text column naming the metric + one numeric value column
        metric_col = next((c for c in text if c.lower() in ("metric", "metric_name", "kpi", "name", "measure")), None)
        # a generic text column only names metrics when the single numeric column is clearly a value
        # column; otherwise it is a dimension (region, status, ...) of raw records
        if metric_col is None and len(numeric) == 1 and \
                str(numeric[0]).lower() in ("value", "val", "metric_value", "kpi_value"):
            metric_col = next((c for c in text if 1 < df[c].nunique() <= max(50, len(df) // 5)), None)
        if metric_col and len(numeric) >= 1:
            value_col = next((c for c in numeric if c.lower() in ("value", "val", "amount", "metric_value")), numeric[0])
            mapping = {"format": "long", "ts_col": ts_col, "metric_col": metric_col, "value_col": value_col}
            notes.append(f"long format: metric names in '{metric_col}', values in '{value_col}'")
            return {"mapping": mapping, "confidence": 0.9, "notes": notes,
                    "metrics": sorted(map(str, df[metric_col].dropna().unique()))[:100]}

        if not numeric:
            return {"mapping": {"ts_col": ts_col}, "confidence": 0.2, "notes": ["no numeric columns found"]}

        # wide format; raw transactional data (irregular timestamps) should be aggregated to KPIs
        mapping: dict = {"format": "wide", "ts_col": ts_col, "metrics": numeric}
        ts = pd.to_datetime(df[ts_col], errors="coerce", utc=True, format="mixed").dropna().sort_values()
        if len(ts) > 3:
            steps = ts.diff().dropna()
            irregular = steps.std() > steps.median() * 0.5 if steps.median() > pd.Timedelta(0) else True
            if irregular or ts.duplicated().any():
                mapping["aggregate"] = {"freq": "1h", "agg": "sum"}
                mapping["count_metric"] = "record_count"
                notes.append("irregular timestamps → looks like raw records; aggregating to hourly KPIs")
        notes.append(f"wide format: {len(numeric)} metric columns")
        return {"mapping": mapping, "confidence": 0.75, "notes": notes, "metrics": numeric}

    @staticmethod
    def _is_identifier(name, s: pd.Series) -> bool:
        """IDs and codes are numeric but meaningless to sum or monitor (order_id, customer_id, zip ...)."""
        n = str(name).lower()
        if n == "id" or n.endswith(("_id", " id", "id_", "_no", "_number", "_code", "zip", "pincode")) or n.startswith("id_"):
            return True
        vals = pd.to_numeric(s, errors="coerce").dropna()
        return len(vals) > 20 and vals.is_unique and (vals % 1 == 0).all() and vals.is_monotonic_increasing

    @staticmethod
    def _is_numeric(s: pd.Series) -> bool:
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            return True
        conv = pd.to_numeric(s, errors="coerce")
        return conv.notna().mean() > 0.9

    @staticmethod
    def _find_timestamp(df: pd.DataFrame) -> str | None:
        for c in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[c]):
                return c
        ranked = sorted(df.columns, key=lambda c: 0 if any(h in str(c).lower() for h in _TS_HINTS) else 1)
        for c in ranked:
            if pd.api.types.is_numeric_dtype(df[c]):
                continue
            parsed = pd.to_datetime(df[c].astype(str).head(200), errors="coerce", utc=True, format="mixed")
            if parsed.notna().mean() > 0.8:
                return c
        return None

    # ── semantics ────────────────────────────────────────────────────────────

    def build(self, schema: list[str] | dict, use_llm: bool = True) -> dict:
        columns    = list(schema) if isinstance(schema, list) else list(schema.keys())
        heuristic  = self._heuristic(columns)
        if not use_llm or not settings.llm_enabled:
            return {**heuristic, "engine": "heuristic"}
        schema_str = json.dumps(schema, indent=2, default=str) if isinstance(schema, dict) else "\n".join(columns)
        raw = self._groq(_PROMPT.format(schema=schema_str)) or self._ollama(_PROMPT.format(schema=schema_str))
        parsed = self._parse(raw, columns) if raw else None
        if parsed:
            return {**parsed, "engine": "llm"}
        return {**heuristic, "engine": "heuristic"}

    @staticmethod
    def _parse(raw: str, columns: list[str]) -> dict | None:
        try:
            match = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(match.group(0)) if match else None
        except (ValueError, json.JSONDecodeError):
            return None
        if not data or not isinstance(data.get("metrics"), list):
            return None
        valid = [m for m in data["metrics"] if isinstance(m, dict) and m.get("column") in columns]
        return {"metrics": valid} if valid else None

    def _groq(self, prompt: str) -> str | None:
        if not self.groq_key:
            return None
        try:
            from groq import Groq
            r = Groq(api_key=self.groq_key, timeout=20).chat.completions.create(
                model=settings.groq_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000, temperature=0.1,
                **({"reasoning_effort": "low"} if "gpt-oss" in settings.groq_model else {}),
            )
            return r.choices[0].message.content.strip()
        except Exception as e:  # noqa: BLE001
            logger.warning("SLAC Groq failed: %s", e)
            return None

    def _ollama(self, prompt: str) -> str | None:
        try:
            import ollama
            client = ollama.Client(host=settings.ollama_url, timeout=30)
            r = client.chat(model=settings.ollama_model, messages=[{"role": "user", "content": prompt}])
            return r["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            logger.debug("SLAC Ollama unavailable: %s", e)
            return None

    @staticmethod
    def _heuristic(columns: list[str]) -> dict:
        metrics = []
        for col in columns:
            lower = str(col).lower().replace("_", " ")
            cat = next((name for name, kws in _CATEGORIES if any(k in lower for k in kws)), "unknown")
            if any(k in lower for k in ("rate", "pct", "percent", "ratio", "margin", "ctr")):
                unit = "percentage"
            elif any(k in lower for k in ("hrs", "hours", "time", "delay", "days", "minutes")):
                unit = "duration"
            elif any(k in lower for k in ("nps", "score", "rating", "csat")):
                unit = "score"
            elif cat in ("revenue", "cost") or any(k in lower for k in ("usd", "inr", "eur", "value", "price")):
                unit = "currency"
            else:
                unit = "count"
            metrics.append({
                "column":           col,
                "business_meaning": str(col).replace("_", " ").title(),
                "unit":             unit,
                "category":         cat,
                "is_kpi":           cat != "unknown",
                "higher_is_better": not any(k in lower for k in _LOWER_IS_BETTER),
            })
        return {"metrics": metrics}
