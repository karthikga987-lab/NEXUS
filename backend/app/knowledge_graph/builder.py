
from __future__ import annotations

from typing import Any

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    Company,
    EventRelationship,
    ProductEvent,
    SourceDocument,
    event_sources,
    relationship_sources,
)


def _safe_value(value: Any) -> Any:
    """Convert dates and enum values into graph-friendly values."""

    if value is None:
        return None

    if hasattr(value, "isoformat"):
        return value.isoformat()

    if hasattr(value, "value"):
        return value.value

    return value


def build_company_graph(
    db: Session,
    company_id: str,
) -> nx.MultiDiGraph:
    """
    Build an evidence-aware knowledge graph for one company.

    Only persisted database relationships are represented.
    Relationship provenance is loaded from relationship_sources.
    Chronological order is never used to infer causation.
    """

    graph = nx.MultiDiGraph()

    company = db.get(Company, company_id)

    if company is None:
        raise ValueError(f"Company not found: {company_id}")

    company_node = f"company:{company.id}"

    graph.add_node(
        company_node,
        node_type="company",
        company_id=company.id,
        name=company.name,
        website=company.website,
        industry=company.industry,
        description=company.description,
        research_status=_safe_value(company.research_status),
    )

    events = (
        db.query(ProductEvent)
        .filter(ProductEvent.company_id == company_id)
        .all()
    )

    sources = (
        db.query(SourceDocument)
        .filter(SourceDocument.company_id == company_id)
        .all()
    )

    event_by_id = {
        event.id: event
        for event in events
    }

    source_by_id = {
        source.id: source
        for source in sources
    }

    # Source document nodes
    for source in sources:
        graph.add_node(
            f"source:{source.id}",
            node_type="source",
            source_id=source.id,
            company_id=source.company_id,
            title=source.title,
            url=source.url,
            publisher=source.publisher,
            source_type=_safe_value(source.source_type),
            publication_date=_safe_value(source.publication_date),
            collected_at=_safe_value(source.collected_at),
            permission_status=_safe_value(source.permission_status),
            reliability=source.reliability,
            processing_status=_safe_value(source.processing_status),
        )

    # Product event nodes and company membership edges
    for event in events:
        event_node = f"event:{event.id}"

        graph.add_node(
            event_node,
            node_type="event",
            event_id=event.id,
            company_id=event.company_id,
            product_name=event.product_name,
            event_type=_safe_value(event.event_type),
            title=event.title,
            description=event.description,
            event_date=_safe_value(event.event_date),
            stated_reason=event.stated_reason,
            reported_outcome=event.reported_outcome,
            evidence_classification=_safe_value(
                event.evidence_classification
            ),
            extraction_confidence=event.extraction_confidence,
            created_at=_safe_value(event.created_at),
            updated_at=_safe_value(event.updated_at),
        )

        graph.add_edge(
            company_node,
            event_node,
            relation_type="HAS_EVENT",
            provenance_status="company_event_membership",
        )

    # Explicit event-to-source associations
    if event_by_id:
        event_source_rows = db.execute(
            select(
                event_sources.c.event_id,
                event_sources.c.source_id,
            ).where(
                event_sources.c.event_id.in_(
                    list(event_by_id.keys())
                )
            )
        ).all()

        for row in event_source_rows:
            event_id = row.event_id
            source_id = row.source_id

            if event_id not in event_by_id:
                continue

            if source_id not in source_by_id:
                continue

            graph.add_edge(
                f"event:{event_id}",
                f"source:{source_id}",
                relation_type="SUPPORTED_BY",
                provenance_status="explicit_event_source_link",
            )

    # Persisted event-to-event relationships
    relationships = (
        db.query(EventRelationship)
        .filter(
            EventRelationship.company_id == company_id,
        )
        .all()
    )

    relationship_ids = [
        relationship.id
        for relationship in relationships
    ]

    # Load relationship provenance in one query.
    provenance_by_relationship: dict[str, list[dict[str, Any]]] = {}

    if relationship_ids:
        provenance_rows = db.execute(
            select(
                relationship_sources.c.relationship_id,
                relationship_sources.c.source_id,
                relationship_sources.c.supporting_quote,
                relationship_sources.c.verification_method,
                relationship_sources.c.created_at,
            ).where(
                relationship_sources.c.relationship_id.in_(
                    relationship_ids
                )
            )
        ).all()

        for row in provenance_rows:
            source = source_by_id.get(row.source_id)

            # Only expose sources belonging to this company's
            # already-loaded source collection.
            if source is None:
                continue

            provenance_by_relationship.setdefault(
                row.relationship_id,
                [],
            ).append(
                {
                    "source_id": source.id,
                    "source_title": source.title,
                    "source_url": source.url,
                    "publisher": source.publisher,
                    "publication_date": _safe_value(
                        source.publication_date
                    ),
                    "supporting_quote": row.supporting_quote,
                    "verification_method": row.verification_method,
                    "provenance_created_at": _safe_value(
                        row.created_at
                    ),
                }
            )

    for relationship in relationships:
        from_event_id = relationship.from_event_id
        to_event_id = relationship.to_event_id

        # Defend against inconsistent or cross-company records.
        if (
            from_event_id not in event_by_id
            or to_event_id not in event_by_id
        ):
            continue

        relation_type = _safe_value(
            relationship.relationship_type
        )

        evidence_status = _safe_value(
            relationship.evidence_status
        )

        provenance = provenance_by_relationship.get(
            relationship.id,
            [],
        )

        supporting_source_ids = sorted(
            {
                item["source_id"]
                for item in provenance
            }
        )

        verification_methods = sorted(
            {
                item["verification_method"]
                for item in provenance
            }
        )

        provenance_available = bool(provenance)

        graph.add_edge(
            f"event:{from_event_id}",
            f"event:{to_event_id}",
            key=relationship.id,
            relationship_id=relationship.id,
            company_id=relationship.company_id,
            relation_type=relation_type,
            relationship_type=relation_type,
            evidence_classification=evidence_status,
            evidence_status=evidence_status,
            explanation=relationship.explanation,
            confidence=relationship.confidence,
            created_at=_safe_value(relationship.created_at),
            provenance_status=(
                "verified_source_provenance_available"
                if provenance_available
                else "relationship_source_provenance_missing"
            ),
            supporting_source_ids=supporting_source_ids,
            supporting_sources=provenance,
            source_provenance_available=provenance_available,
            verification_methods=verification_methods,
            warning=(
                None
                if provenance_available
                else (
                    "No supporting source provenance is stored for "
                    "this relationship. Treat it as an unverified "
                    "database assertion."
                )
            ),
        )

    return graph


def get_graph_summary(graph: nx.MultiDiGraph) -> dict[str, Any]:
    """Return graph statistics and node/edge counts."""

    node_counts = {
        "companies": 0,
        "events": 0,
        "sources": 0,
    }

    for _, attributes in graph.nodes(data=True):
        node_type = attributes.get("node_type")

        if node_type == "company":
            node_counts["companies"] += 1
        elif node_type == "event":
            node_counts["events"] += 1
        elif node_type == "source":
            node_counts["sources"] += 1

    relationship_counts: dict[str, int] = {}

    for _, _, attributes in graph.edges(data=True):
        relation_type = attributes.get("relation_type", "UNKNOWN")

        relationship_counts[relation_type] = (
            relationship_counts.get(relation_type, 0) + 1
        )

    provenance_relationships = sum(
        1
        for _, _, attributes in graph.edges(data=True)
        if attributes.get("relationship_id") is not None
        and attributes.get("source_provenance_available") is True
    )

    relationships_without_provenance = sum(
        1
        for _, _, attributes in graph.edges(data=True)
        if attributes.get("relationship_id") is not None
        and attributes.get("source_provenance_available") is False
    )

    return {
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "node_counts": node_counts,
        "relationship_counts": relationship_counts,
        "relationships_with_provenance": provenance_relationships,
        "relationships_without_provenance": (
            relationships_without_provenance
        ),
    }
