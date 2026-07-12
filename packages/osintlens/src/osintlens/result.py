"""Structured analysis result.

``AnalysisResult`` is the single object returned by :func:`osintlens.analyze`.
It serializes cleanly to JSON and can emit graph-ready nodes/edges for loading
into Neo4j or any property graph.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class Language:
    code: str
    name: str
    confidence: float
    supported: bool


@dataclass
class Risk:
    label: str
    score: int
    confidence: int
    backend: str  # "rules" or "ml"


@dataclass
class AnalysisResult:
    language: Language
    risk: Risk
    iocs: Dict[str, List[str]]
    entities: List[Dict]
    matched_keywords: Dict[str, List[str]]
    text_sha256: str

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    def graph(self, document_id: str) -> Dict[str, List[dict]]:
        """Return graph-ready ``{"nodes": [...], "edges": [...]}`` for this result.

        A document node links to every entity (MENTIONS) and every indicator
        (CONTAINS). Feed the output straight into a Neo4j MERGE loop to knit
        many documents into a shared knowledge graph.
        """
        nodes: List[dict] = [
            {
                "id": document_id,
                "label": "Document",
                "language": self.language.code,
                "risk": self.risk.label,
            }
        ]
        edges: List[dict] = []

        for ent in self.entities:
            node_id = f"{ent['type']}:{ent['text']}"
            nodes.append({"id": node_id, "label": ent["type"], "name": ent["text"]})
            edges.append({"from": document_id, "to": node_id, "type": "MENTIONS"})

        for ioc_type, values in self.iocs.items():
            for value in values:
                node_id = f"{ioc_type}:{value}"
                nodes.append({"id": node_id, "label": "Indicator", "kind": ioc_type, "value": value})
                edges.append({"from": document_id, "to": node_id, "type": "CONTAINS"})

        return {"nodes": nodes, "edges": edges}

    def __repr__(self) -> str:  # concise, readable in a REPL
        ioc_total = sum(len(v) for v in self.iocs.values())
        return (
            f"AnalysisResult(lang={self.language.code}, risk={self.risk.label} "
            f"[{self.risk.confidence}% via {self.risk.backend}], "
            f"entities={len(self.entities)}, iocs={ioc_total})"
        )
