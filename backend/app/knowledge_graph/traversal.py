from __future__ import annotations

from typing import Any

import networkx as nx


def _event_node(event_id: str) -> str:
    return f"event:{event_id}"


def _company_node(company_id: str) -> str:
    return f"company:{company_id}"


def _require_event(
    graph: nx.MultiDiGraph,
    event_id: str,
) -> str:
    """Validate that an event exists in the graph."""

    node_id = _event_node(event_id)

    if node_id not in graph:
        raise ValueError(f"Event not found in graph: {event_id}")

    if graph.nodes[node_id].get("node_type") != "event":
        raise ValueError(f"Node is not an event: {event_id}")

    return node_id


def get_company_events(
    graph: nx.MultiDiGraph,
    company_id: str,
) -> list[dict[str, Any]]:
    """
    Return all events connected to a company.

    Events are sorted chronologically. Events without dates
    appear at the end.

    Chronological order does not imply causation.
    """

    company_id_node = _company_node(company_id)

    if company_id_node not in graph:
        raise ValueError(f"Company not found in graph: {company_id}")

    events = []

    for _, target, edge_data in graph.out_edges(
        company_id_node,
        data=True,
    ):
        if edge_data.get("relation_type") != "HAS_EVENT":
            continue

        attributes = graph.nodes[target]

        if attributes.get("node_type") != "event":
            continue

        event = dict(attributes)
        event["source_ids"] = [
            source["source_id"]
            for source in get_event_sources(
                graph,
                attributes["event_id"],
            )
        ]

        events.append(event)

    events.sort(
        key=lambda event: (
            event.get("event_date") is None,
            event.get("event_date") or "",
        )
    )

    return events


def get_event_sources(
    graph: nx.MultiDiGraph,
    event_id: str,
) -> list[dict[str, Any]]:
    """Return source documents explicitly linked to an event."""

    node_id = _require_event(graph, event_id)

    sources = []

    for _, target, edge_data in graph.out_edges(
        node_id,
        data=True,
    ):
        if edge_data.get("relation_type") != "SUPPORTED_BY":
            continue

        if target not in graph:
            continue

        attributes = graph.nodes[target]

        if attributes.get("node_type") != "source":
            continue

        source = dict(attributes)
        source["link_provenance"] = edge_data.get(
            "provenance_status"
        )

        sources.append(source)

    return sources


def get_event_relationships(
    graph: nx.MultiDiGraph,
    event_id: str,
    direction: str = "both",
) -> list[dict[str, Any]]:
    """
    Return stored relationships connected to an event.

    direction:
      - outgoing: relationships starting at this event
      - incoming: relationships ending at this event
      - both: incoming and outgoing relationships

    HAS_EVENT and SUPPORTED_BY edges are excluded.
    """

    node_id = _require_event(graph, event_id)

    if direction not in {"incoming", "outgoing", "both"}:
        raise ValueError(
            "direction must be 'incoming', 'outgoing', or 'both'"
        )

    relationships = []

    if direction in {"outgoing", "both"}:
        for source, target, edge_key, edge_data in graph.out_edges(
            node_id,
            keys=True,
            data=True,
        ):
            relation_type = edge_data.get("relation_type")

            if relation_type in {"HAS_EVENT", "SUPPORTED_BY"}:
                continue

            relationships.append(
                _format_relationship(
                    source,
                    target,
                    edge_key,
                    edge_data,
                    "outgoing",
                )
            )

    if direction in {"incoming", "both"}:
        for source, target, edge_key, edge_data in graph.in_edges(
            node_id,
            keys=True,
            data=True,
        ):
            relation_type = edge_data.get("relation_type")

            if relation_type in {"HAS_EVENT", "SUPPORTED_BY"}:
                continue

            relationships.append(
                _format_relationship(
                    source,
                    target,
                    edge_key,
                    edge_data,
                    "incoming",
                )
            )

    return relationships


def _format_relationship(
    source: str,
    target: str,
    edge_key: Any,
    edge_data: dict[str, Any],
    direction: str,
) -> dict[str, Any]:
    """Format an event relationship without losing its evidence metadata."""

    return {
        "from_event_id": source.removeprefix("event:"),
        "to_event_id": target.removeprefix("event:"),
        "relation_type": edge_data.get("relation_type"),
        "evidence_classification": edge_data.get(
            "evidence_classification"
        ),
        "explanation": edge_data.get("explanation"),
        "confidence": edge_data.get("confidence"),
        "direction": direction,
        "supporting_source_ids": edge_data.get(
            "supporting_source_ids",
            [],
        ),
        "source_provenance_available": (
            edge_data.get("provenance_status")
            != "relationship_source_ids_not_available"
        ),
        "provenance_status": edge_data.get("provenance_status"),
        "warning": edge_data.get("warning"),
        "edge_key": edge_key,
    }


def get_event_context(
    graph: nx.MultiDiGraph,
    event_id: str,
) -> dict[str, Any]:
    """
    Return an event with its supporting sources
    and incoming/outgoing relationships.
    """

    node_id = _require_event(graph, event_id)

    event = dict(graph.nodes[node_id])

    return {
        "event": event,
        "sources": get_event_sources(graph, event_id),
        "relationships": get_event_relationships(
            graph,
            event_id,
            direction="both",
        ),
    }


def get_graph_events(
    graph: nx.MultiDiGraph,
) -> list[dict[str, Any]]:
    """Return every event node in the graph."""

    events = []

    for _, attributes in graph.nodes(data=True):
        if attributes.get("node_type") == "event":
            events.append(dict(attributes))

    events.sort(
        key=lambda event: (
            event.get("event_date") is None,
            event.get("event_date") or "",
        )
    )

    return events