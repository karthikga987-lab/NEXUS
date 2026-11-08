from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Company, Proposal
from app.schemas.contracts import ProposalAnalyzeIn

router = APIRouter()

@router.post("/analyze", status_code=202)
def analyze_proposal(payload: ProposalAnalyzeIn, db: Session = Depends(get_db)):
    if not db.get(Company, payload.company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    proposal = Proposal(
        company_id=payload.company_id,
        title=payload.title,
        description=payload.description,
        status="queued_placeholder",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    # Member 3 replaces this with retrieval + evidence-grounded analysis.
    return {
        "proposal_id": proposal.id,
        "status": proposal.status,
        "message": "Analysis engine is a placeholder; no recommendation was generated."
    }
