
import unittest

import networkx as nx

from app.knowledge_graph.serialization import graph_to_dict, graph_to_json
from app.knowledge_graph.traversal import (
    get_company_events,
    get_event_context,
    get_event_relationships,
    get_event_sources,
)


class KnowledgeGraphTests(unittest.TestCase):

    def setUp(self):
        self.graph = nx.MultiDiGraph()

        self.graph.add_node(
            "company:company-1",
            node_type="company",
            company_id="company-1",
        )

        self.graph.add_node(
            "event:event-1",
            node_type="event",
            event_id="event-1",
            title="Initial launch",
            event_date="2024-01-10",
        )

        self.graph.add_node(
            "event:event-2",
            node_type="event",
            event_id="event-2",
            title="Feature update",
            event_date="2024-02-10",
        )

        self.graph.add_node(
            "source:source-1",
            node_type="source",
            source_id="source-1",
            title="Official announcement",
            url="https://example.com/source",
        )

        self.graph.add_edge(
            "company:company-1",
            "event:event-1",
            relation_type="HAS_EVENT",
        )

        self.graph.add_edge(
            "company:company-1",
            "event:event-2",
            relation_type="HAS_EVENT",
        )

        self.graph.add_edge(
            "event:event-1",
            "source:source-1",
            relation_type="SUPPORTED_BY",
            provenance_status="explicit_event_source_link",
        )

        self.graph.add_edge(
            "event:event-1",
            "event:event-2",
            key="relationship-1",
            relationship_id="relationship-1",
            relation_type="RESULTED_IN",
            relationship_type="RESULTED_IN",
            evidence_classification="supported_relationship",
            evidence_status="supported_relationship",
            explanation="Stored evidence-supported relationship",
            confidence=0.78,
            provenance_status="relationship_source_ids_not_available",
            supporting_source_ids=[],
            source_provenance_available=False,
        )

    def test_company_events_are_sorted_chronologically(self):
        events = get_company_events(self.graph, "company-1")

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["event_id"], "event-1")
        self.assertEqual(events[1]["event_id"], "event-2")

    def test_event_sources_preserve_source_details(self):
        sources = get_event_sources(self.graph, "event-1")

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["source_id"], "source-1")
        self.assertEqual(
            sources[0]["link_provenance"],
            "explicit_event_source_link",
        )

    def test_relationship_preserves_evidence_metadata(self):
        relationships = get_event_relationships(
            self.graph,
            "event-1",
            direction="outgoing",
        )

        self.assertEqual(len(relationships), 1)

        relationship = relationships[0]

        self.assertEqual(
            relationship["relation_type"],
            "RESULTED_IN",
        )
        self.assertEqual(
            relationship["evidence_classification"],
            "supported_relationship",
        )
        self.assertEqual(relationship["confidence"], 0.78)
        self.assertFalse(
            relationship["source_provenance_available"]
        )

    def test_event_context_contains_sources_and_relationships(self):
        context = get_event_context(self.graph, "event-1")

        self.assertEqual(
            context["event"]["event_id"],
            "event-1",
        )
        self.assertEqual(len(context["sources"]), 1)
        self.assertEqual(len(context["relationships"]), 1)

    def test_invalid_relationship_direction_is_rejected(self):
        with self.assertRaises(ValueError):
            get_event_relationships(
                self.graph,
                "event-1",
                direction="sideways",
            )

    def test_graph_serialization_preserves_relationships(self):
        payload = graph_to_dict(self.graph)

        self.assertEqual(payload["summary"]["node_count"], 4)

        relationship_edges = [
            edge
            for edge in payload["edges"]
            if edge.get("relationship_id") == "relationship-1"
        ]

        self.assertEqual(len(relationship_edges), 1)
        self.assertEqual(
            relationship_edges[0]["evidence_status"],
            "supported_relationship",
        )

        json_output = graph_to_json(self.graph)
        self.assertIn("RESULTED_IN", json_output)


if __name__ == "__main__":
    unittest.main()
