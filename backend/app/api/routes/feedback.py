
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.feedback.analyzer import analyze_feedback
from app.feedback.csv_upload import router as csv_upload_router
from app.db.session import get_db
from app.models import Company, Feedback, SourceDocument
from app.models.entities import feedback_topics
from app.schemas.contracts import FeedbackCreate
from app.feedback.queries import list_public_company_feedback


router = APIRouter()
router.include_router(csv_upload_router)


@router.post("", status_code=201)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
):
    company = db.get(Company, payload.company_id)

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    source = None
    if payload.source_id:
        source = db.get(SourceDocument, payload.source_id)
        if (
            source is None
            or source.company_id != payload.company_id
            or source.permission_status != "public"
        ):
            raise HTTPException(
                status_code=400,
                detail="source_id must refer to a public source belonging to this company.",
            )
        if payload.source_url and payload.source_url not in {
            source.url,
            source.original_url,
        }:
            raise HTTPException(
                status_code=400,
                detail="source_url does not match the selected source record.",
            )

    analysis = analyze_feedback(payload.text)

    item = Feedback(
        company_id=payload.company_id,
        feedback_text=payload.text,
        product_name=payload.product_name,
        source_id=source.id if source else None,
        source_url=(payload.source_url or (source.original_url if source else None)),
        external_reference=payload.external_reference,
        language=payload.language,
        rating=payload.rating,
        created_at_source=payload.created_at_source or payload.feedback_date,
        sentiment=analysis["sentiment"],
        feedback_type=analysis["feedback_type"],
        analysis_status="completed",
    )

    try:
        db.add(item)
        db.flush()

        for topic in analysis["topics"]:
            db.execute(
                feedback_topics.insert().values(
                    feedback_id=item.id,
                    topic=topic,
                )
            )

        db.commit()
        db.refresh(item)

    except Exception:
        db.rollback()
        raise

    return {
        "id": item.id,
        "status": "stored",
        "sentiment": item.sentiment,
        "topics": analysis["topics"],
        "feedback_type": item.feedback_type,
    }


@router.post("/reanalyze/{company_id}")
def reanalyze_feedback(
    company_id: str,
    db: Session = Depends(get_db),
):
    if db.get(Company, company_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    items = list_public_company_feedback(db, company_id)

    updated = 0

    try:
        for item in items:
            analysis = analyze_feedback(item.feedback_text or "")

            item.sentiment = analysis["sentiment"]
            item.feedback_type = analysis["feedback_type"]
            item.analysis_status = "completed"

            db.execute(
                feedback_topics.delete().where(
                    feedback_topics.c.feedback_id == item.id
                )
            )

            for topic in analysis["topics"]:
                db.execute(
                    feedback_topics.insert().values(
                        feedback_id=item.id,
                        topic=topic,
                    )
                )

            updated += 1

        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "company_id": company_id,
        "total_feedback": len(items),
        "updated": updated,
        "status": "completed",
        "message": "Feedback sentiment, type, and topics re-analyzed successfully.",
    }


@router.get("/analysis/{company_id}")
def feedback_analysis(
    company_id: str,
    db: Session = Depends(get_db),
):
    if db.get(Company, company_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    items = list_public_company_feedback(db, company_id)

    sentiment_counts = Counter(
        item.sentiment or "unknown"
        for item in items
    )

    topic_rows = (
        db.execute(
            feedback_topics.select().where(
                feedback_topics.c.feedback_id.in_(
                    [item.id for item in items]
                )
            )
        ).all()
        if items else []
    )

    topic_counts = Counter(
        row.topic for row in topic_rows
    )

    return {
        "company_id": company_id,
        "total_feedback": len(items),
        "sentiment_distribution": dict(sentiment_counts),
        "topic_distribution": dict(topic_counts),
        "analysis_status": "completed",
    }


@router.get("/trends/{company_id}")
def feedback_trends(
    company_id: str,
    db: Session = Depends(get_db),
):
    if db.get(Company, company_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found",
        )

    items = list_public_company_feedback(db, company_id)

    if not items:
        return {
            "company_id": company_id,
            "total_feedback": 0,
            "trends": [],
        }

    topic_rows = db.execute(
        feedback_topics.select().where(
            feedback_topics.c.feedback_id.in_(
                [item.id for item in items]
            )
        )
    ).all()

    feedback_by_id = {
        item.id: item for item in items
    }

    trends = {}

    for row in topic_rows:
        item = feedback_by_id.get(row.feedback_id)

        if item is None:
            continue

        topic = row.topic

        if topic not in trends:
            trends[topic] = {
                "topic": topic,
                "total_feedback": 0,
                "sentiments": {
                    "positive": 0,
                    "negative": 0,
                    "mixed": 0,
                    "neutral": 0,
                    "unknown": 0,
                },
                "evidence": [],
            }

        trends[topic]["total_feedback"] += 1

        sentiment = item.sentiment or "unknown"

        trends[topic]["sentiments"].setdefault(
            sentiment, 0
        )
        trends[topic]["sentiments"][sentiment] += 1

        trends[topic]["evidence"].append({
            "feedback_id": item.id,
            "feedback_text": item.feedback_text,
            "product_name": item.product_name,
            "sentiment": sentiment,
            "rating": item.rating,
            "source_id": item.source_id,
            "source_url": item.source_url,
            "external_reference": item.external_reference,
            "language": item.language,
            "created_at_source": item.created_at_source,
            "collected_at": item.collected_at,
            "feedback_type": item.feedback_type,
            "analysis_status": item.analysis_status,
        })

    return {
        "company_id": company_id,
        "total_feedback": len(items),
        "trends": sorted(
            trends.values(),
            key=lambda item: item["total_feedback"],
            reverse=True,
        ),
    }
