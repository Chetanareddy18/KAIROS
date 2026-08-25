"""Agent 4: NL Reporter — Groq API (primary) → Ollama (fallback) report generation."""
import logging
import os

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("kairos.agent4")

_PROMPT = """
You are KAIROS, an Autonomous Causal Business Intelligence Agent.

ANOMALIES DETECTED:
{anomalies}

ROOT CAUSES IDENTIFIED:
{root_causes}

Write a concise 3-paragraph executive business alert:
1. What happened (metric names, values, severity)
2. Why it happened (causal chain in plain English)
3. Recommended immediate actions

Be direct. Use business language. No bullet points.
""".strip()


class NLReporterAgent:
    def __init__(self):
        self.groq_key     = os.getenv("GROQ_API_KEY", "")
        self.model_groq   = "llama3-8b-8192"
        self.model_ollama = "llama3.1:8b"

    def generate(self, anomalies: list, root_causes: list) -> str:
        if not anomalies:
            return "No anomalies detected in this monitoring cycle."

        prompt = _PROMPT.format(
            anomalies=self._fmt_anomalies(anomalies),
            root_causes=self._fmt_causes(root_causes),
        )
        report = self._groq(prompt) or self._ollama(prompt) or self._fallback(anomalies, root_causes)
        logger.info("Report generated (%d chars)", len(report))
        return report

    def _groq(self, prompt: str) -> str | None:
        if not self.groq_key:
            return None
        try:
            from groq import Groq
            r = Groq(api_key=self.groq_key).chat.completions.create(
                model=self.model_groq,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=512, temperature=0.3,
            )
            return r.choices[0].message.content.strip()
        except Exception as e:
            logger.warning("Groq failed: %s", e)
            return None

    def _ollama(self, prompt: str) -> str | None:
        try:
            import ollama
            r = ollama.chat(model=self.model_ollama, messages=[{"role": "user", "content": prompt}])
            return r["message"]["content"].strip()
        except Exception as e:
            logger.warning("Ollama failed: %s", e)
            return None

    @staticmethod
    def _fallback(anomalies: list, root_causes: list) -> str:
        names = ", ".join({a.metric_name for a in anomalies})
        return (
            f"KAIROS Alert: {len(anomalies)} anomalies in [{names}]. "
            f"{len(root_causes)} causal relationships identified. "
            "Review the dashboard for full details."
        )

    @staticmethod
    def _fmt_anomalies(anomalies: list) -> str:
        return "\n".join(
            f"- {a.metric_name}: observed={a.observed_value:.2f}, "
            f"expected={a.expected_value:.2f}, severity={a.severity}"
            for a in anomalies[:10]
        ) or "None"

    @staticmethod
    def _fmt_causes(causes: list) -> str:
        return "\n".join(
            f"- {getattr(rc, 'cause_metric', '?')} → {getattr(rc, 'effect_metric', '?')} "
            f"(strength={getattr(rc, 'causal_strength', 0):.3f})"
            for rc in causes[:5]
        ) or "None identified"
