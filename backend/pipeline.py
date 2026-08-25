"""LangGraph 5-node state machine orchestrating the full KAIROS pipeline."""
import logging
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

from backend.agents.anomaly_watchman import AnomalyWatchmanAgent
from backend.agents.causal_investigator import CausalInvestigatorAgent
from backend.agents.data_collector import DataCollectorAgent
from backend.agents.messenger import MessengerAgent
from backend.agents.nl_reporter import NLReporterAgent

logger = logging.getLogger("kairos.pipeline")


class PipelineState(TypedDict):
    metrics_collected: int
    anomalies: list
    root_causes: list
    report: str
    alert_sent: bool
    errors: Annotated[list, operator.add]


class KAIROSPipeline:
    def __init__(self, db_path: str = "kairos.duckdb"):
        self.collector    = DataCollectorAgent(db_path)
        self.watchman     = AnomalyWatchmanAgent(db_path)
        self.investigator = CausalInvestigatorAgent(db_path)
        self.reporter     = NLReporterAgent()
        self.messenger    = MessengerAgent()
        self._graph       = self._build_graph()

    # ── Graph construction ─────────────────────────────────────────────────

    def _build_graph(self):
        g = StateGraph(PipelineState)
        g.add_node("collect",     self._collect)
        g.add_node("detect",      self._detect)
        g.add_node("investigate", self._investigate)
        g.add_node("report",      self._report)
        g.add_node("alert",       self._alert)

        g.set_entry_point("collect")
        g.add_edge("collect", "detect")
        g.add_conditional_edges(
            "detect",
            lambda s: "investigate" if s.get("anomalies") else END,
        )
        g.add_edge("investigate", "report")
        g.add_edge("report",      "alert")
        g.add_edge("alert",       END)
        return g.compile()

    # ── Node functions ─────────────────────────────────────────────────────

    def _collect(self, state: PipelineState) -> dict:
        try:
            result = self.collector.collect_all()
            return {"metrics_collected": result["collected"], "errors": result["errors"]}
        except Exception as e:
            logger.error("Collect error: %s", e)
            return {"errors": [str(e)]}

    def _detect(self, state: PipelineState) -> dict:
        try:
            return {"anomalies": self.watchman.detect()}
        except Exception as e:
            logger.error("Detect error: %s", e)
            return {"errors": [str(e)]}

    def _investigate(self, state: PipelineState) -> dict:
        try:
            report = self.investigator.investigate(state["anomalies"])
            return {"root_causes": report.root_causes}
        except Exception as e:
            logger.error("Investigate error: %s", e)
            return {"errors": [str(e)]}

    def _report(self, state: PipelineState) -> dict:
        try:
            text = self.reporter.generate(state["anomalies"], state.get("root_causes", []))
            return {"report": text}
        except Exception as e:
            logger.error("Report error: %s", e)
            return {"report": "Report generation failed.", "errors": [str(e)]}

    def _alert(self, state: PipelineState) -> dict:
        try:
            return {"alert_sent": self.messenger.send(state["report"])}
        except Exception as e:
            logger.error("Alert error: %s", e)
            return {"errors": [str(e)]}

    # ── Public entry point ─────────────────────────────────────────────────

    def run(self) -> PipelineState:
        initial: PipelineState = {
            "metrics_collected": 0,
            "anomalies": [],
            "root_causes": [],
            "report": "",
            "alert_sent": False,
            "errors": [],
        }
        logger.info("KAIROS pipeline triggered")
        result = self._graph.invoke(initial)
        logger.info(
            "Pipeline done — metrics=%d  anomalies=%d  sent=%s",
            result["metrics_collected"],
            len(result.get("anomalies", [])),
            result.get("alert_sent"),
        )
        return result
