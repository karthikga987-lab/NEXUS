from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Company, Feedback
from app.schemas.contracts import FeedbackCreate

router = APIRouter()

@router.post("", status_code=201)
def create_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    item = Feedback(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"id": item.id, "status": "stored"}

@router.get("/analysis/{company_id}")
def feedback_analysis(company_id: str, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    items = db.query(Feedback).filter_by(company_id=company_id).all()
    # Member 4 replaces this summary with validated sentiment/topic analysis.
    return {
        "company_id": company_id,
        "total_feedback": len(items),
        "analysis_status": "not_implemented",
        "message": "Sentiment and topic analysis are placeholders."
    }
