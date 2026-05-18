"""
Neo4j graph ingestion: write extracted entities and relationships.

All writes for a single document are wrapped in one transaction — either
the whole document (nodes + relationships) commits or nothing does.

Schema:
- Nodes: Person, Organization, Location, Product, Entity, Document
- Relationships: MENTIONED_IN, CO_OCCURS
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from py2neo import Graph, Node, Relationship


class Neo4jGraphManager:
    """Manages entity graph in Neo4j with fully transactional document ingestion."""

    def __init__(self, neo4j_uri: str, username: str, password: str, logger: logging.Logger):
        self.logger = logger
        try:
            self.graph = Graph(neo4j_uri, auth=(username, password))
            self.graph.run("RETURN 1")
            logger.info('"Connected to Neo4j"')
        except Exception as e:
            logger.error('"Neo4j connection failed: %s"', e)
            self.graph = None

    def ingest_document(
        self,
        doc_id: str,
        entities: List[Dict],
        source_url: str,
        risk_label: str,
    ) -> None:
        """
        Ingest a document and its entities atomically.

        All Cypher writes happen inside a single transaction — if any step
        fails the transaction is rolled back and no partial data is written.
        """
        if not self.graph:
            return

        tx = self.graph.begin()
        try:
            # ── 1. Create document node ──────────────────────────────────────
            doc_node = Node(
                "Document",
                id=doc_id,
                url=source_url or "",
                risk_label=risk_label,
                indexed_at=datetime.now(timezone.utc).isoformat(),
            )
            tx.create(doc_node)

            # ── 2. MERGE entity nodes + MENTIONED_IN edges ───────────────────
            entity_nodes: List[tuple] = []
            for entity in entities:
                entity_text = entity.get("text", "").strip()
                entity_type = entity.get("type", "Entity")
                if not entity_text:
                    continue

                # MERGE is idempotent — safe to run in the same tx
                result = tx.run(
                    f"MERGE (e:{entity_type} {{text: $text}}) "  # noqa: S608
                    "ON CREATE SET e.created_at = datetime() "
                    "ON MATCH  SET e.last_seen  = datetime() "
                    "RETURN e",
                    text=entity_text,
                ).data()

                if result:
                    entity_node = result[0]["e"]
                else:
                    entity_node = Node(entity_type, text=entity_text)
                    tx.create(entity_node)

                tx.create(Relationship(entity_node, "MENTIONED_IN", doc_node))
                entity_nodes.append((entity_node, entity_text, entity_type))

            # ── 3. CO_OCCURS edges between entities in this document ─────────
            for i, (_, text1, type1) in enumerate(entity_nodes):
                for _, text2, type2 in entity_nodes[i + 1:]:
                    tx.run(
                        f"MATCH (e1:{type1} {{text: $t1}}) "  # noqa: S608
                        f"MATCH (e2:{type2} {{text: $t2}}) "
                        "MERGE (e1)-[r:CO_OCCURS]-(e2) "
                        "ON CREATE SET r.count = 1,           r.first_seen = datetime() "
                        "ON MATCH  SET r.count = r.count + 1, r.last_seen  = datetime()",
                        t1=text1,
                        t2=text2,
                    )

            # ── 4. Commit everything atomically ───────────────────────────────
            tx.commit()
            self.logger.debug(
                '"Neo4j: ingested doc %s with %d entities"', doc_id, len(entity_nodes)
            )

        except Exception as exc:
            try:
                tx.rollback()
            except Exception:
                pass
            self.logger.error('"Neo4j ingest failed, transaction rolled back: %s"', exc)

    def get_entity_graph(self, entity_text: str, depth: int = 2) -> Dict:
        """Return the subgraph reachable from a given entity (uses APOC)."""
        if not self.graph:
            return {}
        try:
            result = self.graph.run(
                "MATCH (e {text: $text}) "
                "CALL apoc.path.subgraphAll(e, {maxLevel: $depth}) "
                "YIELD nodes, relationships "
                "RETURN nodes, relationships",
                text=entity_text,
                depth=depth,
            ).data()
            return result[0] if result else {}
        except Exception as exc:
            self.logger.error('"Neo4j graph query failed: %s"', exc)
            return {}
