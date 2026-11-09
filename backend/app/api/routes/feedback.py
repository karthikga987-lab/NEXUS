
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from collections import Counter

from app.db.session import get_db
from app.models import Company, Feedback
from app.schemas.contracts import FeedbackCreate
from app.feedback.analyzer import analyze_feedback

router = APIRouter()


# 1. Add customer feedback
@router.post("", status_code=201)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db)
):
    # Check whether company exists
    if not db.get(Company, payload.company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    # Analyse feedback
    analysis = analyze_feedback(payload.text)

    # Prepare feedback data
    data = payload.model_dump()

    # Remove these if they are present in the input
    data.pop("sentiment", None)
    data.pop("topic", None)

    # Store feedback with analysis
    item = Feedback(
        **data,
        sentiment=analysis["sentiment"],
        topic=analysis["topic"]
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {
        "id": item.id,
        "status": "stored",
        "sentiment": item.sentiment,
        "topic": item.topic
    }


# 2. Get sentiment and topic analysis
@router.get("/analysis/{company_id}")
def feedback_analysis(
    company_id: str,
    db: Session = Depends(get_db)
):
    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    items = db.query(Feedback).filter_by(
        company_id=company_id
    ).all()

    sentiments = Counter(
        item.sentiment or "uncertain" for item in items
    )

    topics = Counter(
        item.topic or "general" for item in items
    )

    return {
        "company_id": company_id,
        "total_feedback": len(items),
        "sentiment_distribution": dict(sentiments),
        "topic_distribution": dict(topics),
        "analysis_status": "completed"
    }


# 3. Get evidence-linked feedback trends
@router.get("/trends/{company_id}")
def feedback_trends(
    company_id: str,
    db: Session = Depends(get_db)
):
    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    items = db.query(Feedback).filter_by(
        company_id=company_id
    ).all()

    trends = {}

    for item in items:
        topic = item.topic or "general"

        if topic not in trends:
            trends[topic] = {
                "topic": topic,
                "total_feedback": 0,
                "sentiments": {
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0
                },
                "evidence": []
            }

        trends[topic]["total_feedback"] += 1

        sentiment = item.sentiment or "neutral"

        if sentiment not in trends[topic]["sentiments"]:
            trends[topic]["sentiments"][sentiment] = 0

        trends[topic]["sentiments"][sentiment] += 1

        # Attach actual feedback as evidence
        trends[topic]["evidence"].append({
            "feedback_id": item.id,
            "feedback_text": item.text,
            "sentiment": sentiment,
            "rating": item.rating,
            "source_url": item.source_url
        })

    return {
        "company_id": company_id,
        "total_feedback": len(items),
        "trends": sorted(
            trends.values(),
            key=lambda x: x["total_feedback"],
            reverse=True
        )
    }
