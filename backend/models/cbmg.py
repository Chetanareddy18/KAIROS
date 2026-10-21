"""CBMG — Causal Business Metric Graph backed by NetworkX.

Nodes are business metrics; a directed edge cause -> effect carries the causal
weight learned by DYNOTEARS, its lag in time steps, and a bootstrap stability
(confidence). Root-cause analysis walks the graph backwards from an anomalous
metric along the strongest paths.
"""
import json
import logging
import math

import networkx as nx

logger = logging.getLogger("kairos.model.cbmg")


class CausalBusinessMetricGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, metric: str, **attrs) -> None:
        if metric in self.graph:
            self.graph.nodes[metric].update(attrs)
        else:
            self.graph.add_node(metric, **attrs)

    def add_edge(self, cause: str, effect: str, weight: float = 1.0, lag: int = 0,
                 confidence: float = 1.0, sign: int = 1) -> None:
        # keep the strongest relationship if the pair is found at several lags
        if self.graph.has_edge(cause, effect) and abs(self.graph[cause][effect]["weight"]) >= abs(weight):
            return
        self.graph.add_edge(cause, effect, weight=float(weight), lag=int(lag),
                            confidence=float(confidence), sign=int(sign))

    def get_ancestors(self, metric: str) -> list[str]:
        return list(nx.ancestors(self.graph, metric)) if metric in self.graph else []

    def get_root_nodes(self) -> list[str]:
        return [n for n, d in self.graph.in_degree() if d == 0 and self.graph.out_degree(n) > 0]

    def strongest_path(self, cause: str, effect: str, max_len: int = 4) -> tuple[list[str], float, int]:
        """Path maximising the product of |weights| (shortest path on -log|w|)."""
        if cause not in self.graph or effect not in self.graph:
            return [], 0.0, 0
        g = nx.DiGraph()
        for u, v, d in self.graph.edges(data=True):
            w = min(abs(d["weight"]), 0.999)
            if w > 0:
                g.add_edge(u, v, cost=-math.log(w), lag=d["lag"])
        try:
            path = nx.shortest_path(g, cause, effect, weight="cost")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return [], 0.0, 0
        if len(path) - 1 > max_len:
            return [], 0.0, 0
        strength, lag = 1.0, 0
        for u, v in zip(path, path[1:]):
            strength *= min(abs(self.graph[u][v]["weight"]), 1.0)
            lag += self.graph[u][v]["lag"]
        return path, strength, lag

    def to_dict(self) -> dict:
        return {
            "nodes": [{"id": n, **{k: v for k, v in d.items()}} for n, d in self.graph.nodes(data=True)],
            "edges": [
                {"from": u, "to": v, "weight": round(d.get("weight", 1.0), 4), "lag": d.get("lag", 0),
                 "confidence": round(d.get("confidence", 1.0), 3), "sign": d.get("sign", 1)}
                for u, v, d in self.graph.edges(data=True)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CausalBusinessMetricGraph":
        g = cls()
        for n in data.get("nodes", []):
            if isinstance(n, str):
                g.add_node(n)
            else:
                attrs = dict(n)
                g.add_node(attrs.pop("id"), **attrs)
        for e in data.get("edges", []):
            g.add_edge(e["from"], e["to"], weight=e.get("weight", 1.0), lag=e.get("lag", 0),
                       confidence=e.get("confidence", 1.0), sign=e.get("sign", 1))
        return g

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)

    def visualize(self, output_path: str = "docs/assets/cbmg.png") -> None:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            pos = nx.spring_layout(self.graph, seed=42)
            colors = ["#C04040" if self.graph.nodes[n].get("anomalous") else "#1E7A78" for n in self.graph]
            plt.figure(figsize=(12, 8))
            nx.draw_networkx(self.graph, pos, node_color=colors, font_color="white",
                             edge_color="#D4B896", arrows=True, node_size=2200, font_size=8)
            labels = {(u, v): f"{d['weight']:.2f} (lag {d['lag']})" for u, v, d in self.graph.edges(data=True)}
            nx.draw_networkx_edge_labels(self.graph, pos, edge_labels=labels, font_size=7)
            plt.title("KAIROS — Causal Business Metric Graph (CBMG)")
            plt.axis("off")
            plt.tight_layout()
            plt.savefig(output_path, dpi=150)
            plt.close()
            logger.info("CBMG saved to %s", output_path)
        except Exception as e:  # noqa: BLE001
            logger.error("CBMG visualize failed: %s", e)
