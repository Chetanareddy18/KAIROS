"""SLAC — Semantic Layer Auto-Construction via LLM schema inference."""
import json
import logging
import os

logger = logging.getLogger("kairos.model.slac")

_PROMPT = """
You are a business intelligence expert. Given the schema below, infer the business meaning of each column.

Schema:
{schema}

Respond as JSON only:
{{
  "metrics": [
    {{
      "column": "column_name",
      "business_meaning": "plain English description",
      "unit": "currency|count|percentage|ratio",
      "category": "revenue|cost|volume|quality|engagement|unknown",
      "is_kpi": true
    }}
  ]
}}
""".strip()

_REVENUE  = {"revenue", "sales", "gmv", "mrr", "arr", "income", "turnover"}
_COST     = {"cost", "expense", "spend", "cogs", "opex", "capex"}
_VOLUME   = {"orders", "transactions", "units", "count", "qty", "quantity", "visits"}
_QUALITY  = {"nps", "csat", "rating", "score", "defect", "return", "churn"}


class SemanticLayerAutoConstructor:
    def __init__(self):
        self.groq_key = os.getenv("GROQ_API_KEY", "")

    def build(self, schema: list[str] | dict) -> dict:
        schema_str = json.dumps(schema, indent=2) if isinstance(schema, dict) else "\n".join(schema)
        columns    = list(schema) if isinstance(schema, list) else list(schema.keys())
        prompt     = _PROMPT.format(schema=schema_str)

        raw = self._groq(prompt) or self._ollama(prompt)
        if raw:
            try:
                start = raw.index("{")
                return json.loads(raw[start:])
            except (ValueError, json.JSONDecodeError):
                pass

        return self._heuristic(columns)

    def _groq(self, prompt: str) -> str | None:
        if not self.groq_key:
            return None
        try:
            from groq import Groq
            r = Groq(api_key=self.groq_key).chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024, temperature=0.1,
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("SLAC Groq failed: %s", e)
            return None

    def _ollama(self, prompt: str) -> str | None:
        try:
            import ollama
            r = ollama.chat(model="llama3.1:8b", messages=[{"role": "user", "content": prompt}])
            return r["message"]["content"].strip()
        except Exception as e:
            logger.warning("SLAC Ollama failed: %s", e)
            return None

    @staticmethod
    def _heuristic(columns: list[str]) -> dict:
        metrics = []
        for col in columns:
            lower = col.lower().replace("_", " ")
            cat   = "unknown"
            for kw in _REVENUE:
                if kw in lower: cat = "revenue"; break
            for kw in _COST:
                if kw in lower: cat = "cost"; break
            for kw in _VOLUME:
                if kw in lower: cat = "volume"; break
            for kw in _QUALITY:
                if kw in lower: cat = "quality"; break
            metrics.append({
                "column":           col,
                "business_meaning": col.replace("_", " ").title(),
                "unit":             "currency" if cat in ("revenue", "cost") else "count",
                "category":         cat,
                "is_kpi":           cat != "unknown",
            })
        return {"metrics": metrics}
