"""CBMG — Causal Business Metric Graph backed by NetworkX."""
import json
import logging

import networkx as nx

logger = logging.getLogger("kairos.model.cbmg")


class CausalBusinessMetricGraph:
    def __init__(self):
        self.graph = nx.DiGraph()

    def add_node(self, metric: str, **attrs) -> None:
        self.graph.add_node(metric, **attrs)

    def add_edge(self, cause: str, effect: str, weight: float = 1.0, lag: int = 0) -> None:
        self.graph.add_edge(cause, effect, weight=weight, lag=lag)

    def get_ancestors(self, metric: str) -> list[str]:
        return list(nx.ancestors(self.graph, metric))

    def get_root_nodes(self) -> list[str]:
        return [n for n, d in self.graph.in_degree() if d == 0]

    def to_dict(self) -> dict:
        return {
            "nodes": list(self.graph.nodes()),
            "edges": [
                {"from": u, "to": v, "weight": d.get("weight", 1.0), "lag": d.get("lag", 0)}
                for u, v, d in self.graph.edges(data=True)
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def visualize(self, output_path: str = "docs/assets/cbmg.png") -> None:
        try:
            import matplotlib.pyplot as plt
            pos = nx.spring_layout(self.graph, seed=42)
            plt.figure(figsize=(12, 8))
            nx.draw_networkx(
                self.graph, pos,
                node_color="#1E7A78", font_color="white",
                edge_color="#D4B896", arrows=True,
                node_size=2000, font_size=9,
            )
            plt.title("KAIROS — Causal Business Metric Graph (CBMG)")
            plt.axis("off")
            plt.tight_layout()
            plt.savefig(output_path, dpi=150)
            plt.close()
            logger.info("CBMG saved to %s", output_path)
        except Exception as e:
            logger.error("CBMG visualize failed: %s", e)
