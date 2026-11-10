from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

import networkx as nx


def _json_safe(value: Any) -> Any:
    """Convert common Python values into JSON-compatible values."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, (UUID, Enum)):
        return str(value.value if isinstance(value, Enum) else value)

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    return str(value)


def graph_to_dict(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """
    Convert a NetworkX graph into a JSON-compatible dictionary.

    Preserves:
      - Node IDs and attributes
      - Edge source and target IDs
      - Relationship types
      - Evidence classifications
      - Provenance metadata
      - Multi-edge keys
    """

    nodes = []

    for node_id, attributes in graph.nodes(data=True):
        nodes.append(
            {
                "id": str(node_id),
                **_json_safe(dict(attributes)),
            }
        )

    edges = []

    if graph.is_multigraph():
        for source, target, key, attributes in graph.edges(
            keys=True,
            data=True,
        ):
            edges.append(
                {
                    "id": f"{source}->{target}:{key}",
                    "source": str(source),
                    "target": str(target),
                    "key": _json_safe(key),
                    **_json_safe(dict(attributes)),
                }
            )
    else:
        for source, target, attributes in graph.edges(data=True):
            edges.append(
                {
                    "id": f"{source}->{target}",
                    "source": str(source),
                    "target": str(target),
                    **_json_safe(dict(attributes)),
                }
            )

    return {
        "schema_version": "1.0",
        "directed": graph.is_directed(),
        "multigraph": graph.is_multigraph(),
        "summary": {
            "node_count": graph.number_of_nodes(),
            "edge_count": graph.number_of_edges(),
        },
        "nodes": nodes,
        "edges": edges,
    }


def graph_to_json(
    graph: nx.MultiDiGraph,
    indent: int | None = 2,
) -> str:
    """Serialize a NetworkX graph into a JSON string."""

    payload = graph_to_dict(graph)

    return json.dumps(
        payload,
        indent=indent,
        ensure_ascii=False,
        allow_nan=False,
    )