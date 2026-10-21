"""LangGraph 5-node state machine orchestrating the full KAIROS pipeline.

collect -> detect -> (new alert-worthy anomalies?) -> investigate -> report -> alert

Alert gating — what keeps KAIROS from spamming:
  * only anomalies seen for the first time this run (persisted in DuckDB),
  * only recent ones (within the alert look-back of each series' newest point),
  * at or above the configured minimum severity,
  * and not for a metric already alerted within the cooldown window.
"""
from __future__ import annotations

import json
import logging
import operator
import threading
from typing import Annotated, TypedDict

import pandas as pd
from langgraph.graph import END, StateGraph

from backend.agents.anomaly_watchman import AnomalyResult, AnomalyWatchmanAgent
from backend.agents.causal_investigator import CausalInvestigatorAgent, RootCauseReport
from backend.agents.data_collector import DataCollectorAgent
from backend.agents.messenger import MessengerAgent
from backend.agents.nl_reporter import NLReporterAgent
from backend.config import settings
from backend.db import Database, get_db, utcnow
from backend.models.anomaly import severity_at_least

logger = logging.getLogger("kairos.pipeline")

ALERT_LOOKBACK_HOURS = 24


class PipelineState(TypedDict, total=False):
    trigger:           str
    metrics_collected: int
    collect_details:   list
    anomalies:         list
    new_anomalies:     list
    alertable:         list
    investigation:     object
    root_causes:       list
    report:            str
    report_meta:       dict
    alert_sent:        bool
    errors:            Annotated[list, operator.add]


class KAIROSPipeline:
    def __init__(self, db: Database | str | None = None):
        self.db           = db if isinstance(db, Database) else get_db(db) if isinstance(db, str) else get_db()
        self.collector    = DataCollectorAgent(self.db)
        self.watchman     = AnomalyWatchmanAgent(self.db)
        self.investigator = CausalInvestigatorAgent(self.db)
        self.reporter     = NLReporterAgent()
        self.messenger    = MessengerAgent(self.db)
        self._graph       = self._build_graph()
        self._run_lock    = threading.Lock()
        self.running      = False
        self.last_investigation: RootCauseReport | None = None
        self.last_report: dict | None = None

    # ── graph ────────────────────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(PipelineState)
        g.add_node("collect",     self._collect)
        g.add_node("detect",      self._detect)
        g.add_node("investigate", self._investigate)
        g.add_node("report",      self._report)
        g.add_node("alert",       self._alert)
        g.set_entry_point("collect")
        g.add_edge("collect", "detect")
        g.add_conditional_edges("detect", lambda s: "investigate" if s.get("alertable") else END)
        g.add_edge("investigate", "report")
        g.add_edge("report",      "alert")
        g.add_edge("alert",       END)
        return g.compile()

    # ── nodes ────────────────────────────────────────────────────────────────

    def _collect(self, state: PipelineState) -> dict:
        try:
            result = self.collector.collect_all()
            return {"metrics_collected": result["collected"], "collect_details": result["sources"],
                    "errors": [f"{e['source']}: {e['error']}" for e in result["errors"]]}
        except Exception as e:  # noqa: BLE001
            logger.exception("Collect error")
            return {"metrics_collected": 0, "errors": [f"collect: {e}"]}

    def _detect(self, state: PipelineState) -> dict:
        try:
            anomalies = self.watchman.detect()
            new = [a for a in anomalies if a.is_new]
            return {"anomalies": anomalies, "new_anomalies": new, "alertable": self._alertable(new)}
        except Exception as e:  # noqa: BLE001
            logger.exception("Detect error")
            return {"anomalies": [], "new_anomalies": [], "alertable": [], "errors": [f"detect: {e}"]}

    def _alertable(self, new: list[AnomalyResult]) -> list[AnomalyResult]:
        if not new:
            return []
        last_ts = {(s, m): pd.Timestamp(t) for s, m, t in self.db.execute(
            "SELECT source, metric_name, max(timestamp) FROM metrics GROUP BY 1, 2")}
        cooled = {(s, m) for s, m in self.db.execute(
            "SELECT DISTINCT source, metric_name FROM anomalies WHERE alerted AND "
            "detected_at >= now() - to_minutes(CAST(? AS BIGINT))", [settings.alert_cooldown_min])}
        out = []
        for a in new:
            newest = last_ts.get((a.source, a.metric_name))
            recent = newest is None or pd.Timestamp(a.timestamp) >= newest - pd.Timedelta(hours=ALERT_LOOKBACK_HOURS)
            if recent and severity_at_least(a.severity, settings.alert_min_severity) \
                    and (a.source, a.metric_name) not in cooled:
                out.append(a)
        return out

    def _investigate(self, state: PipelineState) -> dict:
        try:
            # investigate every recent anomaly (not only alertable) so upstream causes are visible
            recent = self.watchman.recent(ALERT_LOOKBACK_HOURS) or state["alertable"]
            report = self.investigator.investigate(recent)
            self.last_investigation = report
            return {"investigation": report, "root_causes": report.root_causes}
        except Exception as e:  # noqa: BLE001
            logger.exception("Investigate error")
            return {"root_causes": [], "errors": [f"investigate: {e}"]}

    def _report(self, state: PipelineState) -> dict:
        try:
            inv = state.get("investigation")
            result = self.reporter.generate_report(
                state["alertable"], state.get("root_causes", []), getattr(inv, "origins", []))
            self.last_report = {**result.to_dict(), "generated_at": utcnow().isoformat()}
            return {"report": result.text, "report_meta": result.to_dict()}
        except Exception as e:  # noqa: BLE001
            logger.exception("Report error")
            return {"report": "Report generation failed.", "errors": [f"report: {e}"]}

    def _alert(self, state: PipelineState) -> dict:
        try:
            meta = state.get("report_meta", {})
            sent = self.messenger.send(state["report"], anomaly_count=len(state["alertable"]),
                                       verified=meta.get("verified"), model=meta.get("engine"))
            self._mark_alerted(state["alertable"])
            return {"alert_sent": sent}
        except Exception as e:  # noqa: BLE001
            logger.exception("Alert error")
            return {"alert_sent": False, "errors": [f"alert: {e}"]}

    def _mark_alerted(self, anomalies: list[AnomalyResult]) -> None:
        for a in anomalies:
            self.db.execute(
                "UPDATE anomalies SET alerted = TRUE WHERE source = ? AND metric_name = ? AND timestamp = ?",
                [a.source, a.metric_name, pd.Timestamp(a.timestamp).to_pydatetime()],
            )

    # ── public entry point ───────────────────────────────────────────────────

    def run(self, trigger: str = "schedule") -> dict:
        if not self._run_lock.acquire(blocking=False):
            logger.info("Pipeline already running — skipping trigger '%s'", trigger)
            return {"status": "skipped", "reason": "already running"}
        started = utcnow()
        self.running = True
        try:
            logger.info("KAIROS pipeline triggered (%s)", trigger)
            result = self._graph.invoke({"trigger": trigger, "errors": []})
            summary = self._summarise(result)
            self._log_run(started, trigger, summary)
            logger.info("Pipeline done — rows=%d anomalies=%d new=%d alertable=%d sent=%s",
                        summary["metrics_collected"], summary["anomalies_found"], summary["new_anomalies"],
                        summary["alertable"], summary["alert_sent"])
            return summary
        finally:
            self.running = False
            self._run_lock.release()

    @staticmethod
    def _summarise(result: dict) -> dict:
        inv = result.get("investigation")
        return {
            "status":            "ok" if not result.get("errors") else "partial",
            "metrics_collected": result.get("metrics_collected", 0),
            "sources":           result.get("collect_details", []),
            "anomalies_found":   len(result.get("anomalies", [])),
            "new_anomalies":     len(result.get("new_anomalies", [])),
            "alertable":         len(result.get("alertable", [])),
            "root_causes":       [rc.to_dict() for rc in result.get("root_causes", [])][:10],
            "origins":           getattr(inv, "origins", []),
            "report":            result.get("report", ""),
            "report_meta":       result.get("report_meta", {}),
            "alert_sent":        result.get("alert_sent", False),
            "errors":            result.get("errors", []),
        }

    def _log_run(self, started, trigger: str, s: dict) -> None:
        self.db.execute(
            "INSERT INTO pipeline_runs (started_at, finished_at, trigger, status, metrics_collected, "
            "anomalies_found, new_anomalies, alert_sent, errors, result) VALUES (?, now(), ?, ?, ?, ?, ?, ?, ?, ?)",
            [started, trigger, s["status"], s["metrics_collected"], s["anomalies_found"], s["new_anomalies"],
             s["alert_sent"], json.dumps(s["errors"]), json.dumps(s, default=str)],
        )

    def runs(self, limit: int = 20) -> list[dict]:
        df = self.db.df(
            "SELECT id, started_at, finished_at, trigger, status, metrics_collected, anomalies_found, "
            "new_anomalies, alert_sent, errors FROM pipeline_runs ORDER BY id DESC LIMIT ?", [limit])
        out = []
        for r in df.to_dict(orient="records"):
            r["started_at"]  = pd.Timestamp(r["started_at"]).isoformat() if r["started_at"] is not None else None
            r["finished_at"] = pd.Timestamp(r["finished_at"]).isoformat() if r["finished_at"] is not None else None
            r["errors"] = json.loads(r["errors"]) if r["errors"] else []
            r["duration_s"] = (round((pd.Timestamp(r["finished_at"]) - pd.Timestamp(r["started_at"])).total_seconds(), 2)
                               if r["started_at"] and r["finished_at"] else None)
            out.append(r)
        return out
