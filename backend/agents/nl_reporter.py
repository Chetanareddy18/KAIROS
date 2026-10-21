"""Agent 4: NL Reporter — LLM report generation under an LLM-Modulo verifier.

LLM-Modulo (Kambhampati et al., 2024): the LLM *proposes*, a sound external
critic *verifies*. Here the critic checks every number and metric name in the
draft against the facts the pipeline computed. A draft that cites a number not
in the data (a hallucination) or an unknown metric is sent back with the
critique; if it still fails, a deterministic template report — verified by
construction — is used. Every report records whether it passed verification.

Engines: Groq (cloud, free tier) -> Ollama (local) -> template.
"""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field

from backend.config import settings
from backend.models.anomaly import SEVERITY_ORDER
from backend.models.slac import SemanticLayerAutoConstructor

logger = logging.getLogger("kairos.agent4")

_PROMPT = """
You are KAIROS, an Autonomous Causal Business Intelligence Agent, writing an alert for executives.

FACTS (use only these numbers — do not invent or round differently):
{facts}

Write a concise 3-paragraph executive business alert:
1. What happened — metric names exactly as written above, observed vs expected values, severity.
2. Why it happened — the causal chain in plain English, origin first.
3. Recommended immediate actions (concrete, 2-3 actions).

Be direct, business language, no bullet points, no markdown headings, under 220 words.
""".strip()

_RETRY = """
Your previous draft failed fact verification:
{issues}

Rewrite it using ONLY numbers and metric names that appear in the FACTS. Same structure.
""".strip()

_NUM_RE = re.compile(r"(?<![\w.])[-+]?\$?\d[\d,]*(?:\.\d+)?%?")
_IDENT_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


@dataclass
class ReportResult:
    text:     str
    verified: bool
    engine:   str
    attempts: int = 1
    issues:   list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class NLReporterAgent:
    def __init__(self):
        self.groq_key     = settings.groq_api_key
        self.model_groq   = settings.groq_model
        self.model_ollama = settings.ollama_model
        self._semantics   = SemanticLayerAutoConstructor()

    # ── public ───────────────────────────────────────────────────────────────

    def generate(self, anomalies: list, root_causes: list, origins: list | None = None) -> str:
        return self.generate_report(anomalies, root_causes, origins).text

    def generate_report(self, anomalies: list, root_causes: list, origins: list | None = None) -> ReportResult:
        if not anomalies:
            return ReportResult("No anomalies detected in this monitoring cycle.", True, "none")
        top     = self._top_anomalies(anomalies)
        facts   = self._facts(top, root_causes, origins or [], len(anomalies))
        allowed = self._allowed_numbers(top, root_causes, len(anomalies))
        known   = {a.metric_name for a in anomalies} | {
            m for rc in root_causes for m in getattr(rc, "path", []) or [rc.cause_metric, rc.effect_metric]
        }

        if settings.llm_enabled:
            prompt = _PROMPT.format(facts=facts)
            issues: list[str] = []
            for attempt in (1, 2):
                draft, engine = self._llm(prompt)
                if not draft:
                    break
                issues = self.verify(draft, allowed, known)
                if not issues:
                    logger.info("Report verified (%s, attempt %d)", engine, attempt)
                    return ReportResult(draft, True, engine, attempt)
                logger.warning("LLM-Modulo rejected draft %d: %s", attempt, issues[:3])
                prompt = _PROMPT.format(facts=facts) + "\n\n" + _RETRY.format(issues="\n".join(issues[:8]))
            if issues:
                text = self._template(top, root_causes, origins or [], len(anomalies))
                return ReportResult(text, True, "template (LLM draft failed verification)", 3, issues[:8])

        return ReportResult(self._template(top, root_causes, origins or [], len(anomalies)), True, "template")

    # ── LLM-Modulo critic ────────────────────────────────────────────────────

    @staticmethod
    def verify(text: str, allowed: list[float], known_metrics: set[str]) -> list[str]:
        issues = []
        for raw in _NUM_RE.findall(text):
            token = raw.replace("$", "").replace(",", "")
            pct = token.endswith("%")
            try:
                val = float(token.rstrip("%"))
            except ValueError:
                continue
            if not pct and abs(val) <= 12 and float(val).is_integer():
                continue          # small integers: list numbering, counts of actions, hours of day
            body = token.rstrip("%")
            decimals = len(body.split(".", 1)[1]) if "." in body else 0
            if not any(_close(val, a, decimals) for a in allowed):
                issues.append(f"number {raw} is not supported by the facts")
        for ident in set(_IDENT_RE.findall(text)):
            if ident not in known_metrics:
                issues.append(f"metric '{ident}' does not exist in the data")
        return issues

    # ── facts ────────────────────────────────────────────────────────────────

    @staticmethod
    def _top_anomalies(anomalies: list, n: int = 8) -> list:
        """Most severe anomaly per metric, most severe metrics first."""
        best: dict = {}
        for a in anomalies:
            k = (a.source, a.metric_name)
            if k not in best or abs(a.deviation_score) > abs(best[k].deviation_score):
                best[k] = a
        ranked = sorted(best.values(), key=lambda a: (SEVERITY_ORDER.index(a.severity), abs(a.deviation_score)),
                        reverse=True)
        return ranked[:n]

    @staticmethod
    def _pct(a) -> float:
        return (a.observed_value - a.expected_value) / abs(a.expected_value) * 100 if a.expected_value else 0.0

    def _facts(self, top: list, root_causes: list, origins: list, total: int) -> str:
        lines = [f"Total anomalous points this cycle: {total}"]
        for a in top:
            lines.append(
                f"- {a.metric_name} (source {a.source}): observed {a.observed_value:,.2f}, expected "
                f"{a.expected_value:,.2f}, change {self._pct(a):+.1f}%, severity {a.severity}, "
                f"at {str(a.timestamp)[:16]}"
            )
        if origins:
            lines.append(f"Most likely origin metric(s): {', '.join(origins)}")
        for rc in root_causes[:5]:
            path = " → ".join(getattr(rc, "path", None) or [rc.cause_metric, rc.effect_metric])
            lines.append(f"- causal chain: {path}; strength {rc.causal_strength:.2f}; "
                         f"confidence {rc.confidence * 100:.0f}%; lag {rc.lag_hours:g} hours")
        return "\n".join(lines)

    def _allowed_numbers(self, top: list, root_causes: list, total: int) -> list[float]:
        nums = [float(total), float(len(top)), 100.0]
        for a in top:
            pct = self._pct(a)
            nums += [a.observed_value, a.expected_value, pct, abs(pct), abs(a.deviation_score),
                     a.observed_value - a.expected_value, abs(a.observed_value - a.expected_value)]
            ts = str(a.timestamp)
            nums += [float(x) for x in re.findall(r"\d+", ts[:16])]
        for rc in root_causes[:5]:
            nums += [rc.causal_strength, rc.confidence, rc.confidence * 100, rc.lag_hours]
        return nums

    # ── engines ──────────────────────────────────────────────────────────────

    def _llm(self, prompt: str) -> tuple[str | None, str]:
        text = self._groq(prompt)
        if text:
            return text, f"groq:{self.model_groq}"
        text = self._ollama(prompt)
        if text:
            return text, f"ollama:{self.model_ollama}"
        return None, "none"

    def _groq(self, prompt: str) -> str | None:
        if not self.groq_key:
            return None
        try:
            from groq import Groq
            extra = {"reasoning_effort": "low"} if "gpt-oss" in self.model_groq else {}
            r = Groq(api_key=self.groq_key, timeout=30).chat.completions.create(
                model=self.model_groq,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500, temperature=0.2, **extra,   # headroom for reasoning-model tokens
            )
            text = (r.choices[0].message.content or "").strip()
            return text.replace("**", "").replace("__", "") or None
        except Exception as e:  # noqa: BLE001
            logger.warning("Groq failed: %s", e)
            return None

    def _ollama(self, prompt: str) -> str | None:
        try:
            import ollama
            client = ollama.Client(host=settings.ollama_url, timeout=60)
            r = client.chat(model=self.model_ollama, messages=[{"role": "user", "content": prompt}])
            return r["message"]["content"].strip()
        except Exception as e:  # noqa: BLE001
            logger.debug("Ollama unavailable: %s", e)
            return None

    # ── deterministic template (verified by construction) ────────────────────

    def _template(self, top: list, root_causes: list, origins: list, total: int) -> str:
        sem = {m["column"]: m for m in self._semantics.build([a.metric_name for a in top], use_llm=False)["metrics"]}

        def phrase(a) -> str:
            up = a.observed_value > a.expected_value
            good = sem.get(a.metric_name, {}).get("higher_is_better", True)
            verb = "spiked to" if up else "dropped to"
            tone = "" if up == good else " — an unfavourable move"
            return (f"{a.metric_name} {verb} {a.observed_value:,.2f} against an expected "
                    f"{a.expected_value:,.2f} ({self._pct(a):+.1f}%, {a.severity}){tone}")

        crit = [a for a in top if a.severity in ("critical", "high")]
        p1 = (f"KAIROS detected {total} anomalous data points. "
              + "; ".join(phrase(a) for a in top[:4]) + ".")
        if root_causes:
            rc = root_causes[0]
            chain = " → ".join(rc.path or [rc.cause_metric, rc.effect_metric])
            p2 = (f"Causal analysis points to {', '.join(origins) if origins else rc.cause_metric} as the most "
                  f"likely origin. The strongest chain is {chain}, with strength {rc.causal_strength:.2f} and "
                  f"{rc.confidence * 100:.0f}% confidence, propagating over about {rc.lag_hours:g} "
                  f"hour{'' if rc.lag_hours == 1 else 's'}.")
            other = next((r for r in root_causes[1:] if r.cause_metric != rc.cause_metric), None)
            if other is not None:
                p2 += (f" Independently, {' → '.join(other.path or [other.cause_metric, other.effect_metric])} "
                       f"explains a second group of anomalies.")
        else:
            p2 = ("No upstream causal driver was found in the connected metrics, so these anomalies appear to be "
                  "independent events or driven by a factor KAIROS does not yet monitor.")
        target = origins[0] if origins else (root_causes[0].cause_metric if root_causes else top[0].metric_name)
        p3 = (f"Recommended actions: first, investigate what changed in {target} around the time of the anomaly "
              f"and confirm with its owning team; second, "
              + (f"prioritise the {len(crit)} high-severity metric{'' if len(crit) == 1 else 's'} "
                 "and brief their owners today; "
                 if crit else "monitor the affected metrics over the next cycles; ")
              + "third, open the KAIROS dashboard to review the causal graph before taking corrective action.")
        return "\n\n".join([p1, p2, p3])


def _close(value: float, allowed: float, decimals: int = 2) -> bool:
    """Does `value`, as written with `decimals` decimal places, faithfully state `allowed`?

    A faithful writer rounds the true number to the precision they print, so the check is
    "allowed rounds to value at that precision" — 3.97 may be written 3.97, 4.0 or 4, but 3.78 or
    7.03 never match 3.974 / 6.713. A tiny relative slack absorbs float noise and rounding of
    already-rounded facts (e.g. a percentage computed from rounded values).
    """
    step = 0.5 * 10 ** (-decimals)
    return abs(value - allowed) <= step + abs(allowed) * 1e-3 + 1e-9
