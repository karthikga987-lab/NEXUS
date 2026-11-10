from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.knowledge_graph.builder import build_company_graph
from app.knowledge_graph.serialization import graph_to_dict
from app.knowledge_graph.traversal import (
    get_company_events,
    get_event_context,
    get_event_relationships,
)

router = APIRouter()


def _build_graph_or_404(db: Session, company_id: str):
    """Build a company's graph or return a 404 response."""

    try:
        return build_company_graph(
            db=db,
            company_id=company_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get("/{company_id}/knowledge-graph")
def get_company_knowledge_graph(
    company_id: str,
    db: Session = Depends(get_db),
):
    """Return the complete evidence-aware company knowledge graph."""

    graph = _build_graph_or_404(db, company_id)
    return graph_to_dict(graph)


@router.get("/{company_id}/knowledge-graph/events")
def get_company_event_timeline(
    company_id: str,
    db: Session = Depends(get_db),
):
    """
    Return all company events in chronological order.

    Each event includes the IDs of its explicitly linked sources.
    Chronological order does not imply causation.
    """

    graph = _build_graph_or_404(db, company_id)

    return {
        "company_id": company_id,
        "event_count": 0,
        "events": [],
    } | {
        "event_count": len(events := get_company_events(graph, company_id)),
        "events": events,
    }


@router.get("/{company_id}/knowledge-graph/events/{event_id}")
def get_company_event_details(
    company_id: str,
    event_id: str,
    db: Session = Depends(get_db),
):
    """Return one event with its supporting sources and relationships."""

    graph = _build_graph_or_404(db, company_id)

    try:
        return get_event_context(graph, event_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc


@router.get(
    "/{company_id}/knowledge-graph/events/{event_id}/relationships"
)
def get_company_event_relationships(
    company_id: str,
    event_id: str,
    direction: str = Query(
        default="both",
        pattern="^(incoming|outgoing|both)$",
        description="Relationship direction: incoming, outgoing, or both.",
    ),
    db: Session = Depends(get_db),
):
    """Return stored relationships for an event with evidence metadata."""

    graph = _build_graph_or_404(db, company_id)

    try:
        relationships = get_event_relationships(
            graph=graph,
            event_id=event_id,
            direction=direction,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    return {
        "company_id": company_id,
        "event_id": event_id,
        "direction": direction,
        "relationship_count": len(relationships),
        "relationships": relationships,
    }