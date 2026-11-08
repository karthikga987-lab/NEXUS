from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models import Company, SourceDocument, ProductEvent
from app.schemas.contracts import CompanyCreate, CompanyOut, SourceOut, EventOut

router = APIRouter()

@router.post("", response_model=CompanyOut, status_code=201)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company = Company(**payload.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company

@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).order_by(Company.created_at.desc()).all()

@router.get("/{company_id}", response_model=CompanyOut)
def get_company(company_id: str, db: Session = Depends(get_db)):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return company

@router.post("/{company_id}/research")
def start_research(company_id: str, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    # Member 2 replaces this placeholder with a permitted research job.
    return {"company_id": company_id, "status": "not_implemented", "message": "Research pipeline is a placeholder."}

@router.get("/{company_id}/sources", response_model=list[SourceOut])
def list_sources(company_id: str, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    return db.query(SourceDocument).filter_by(company_id=company_id).all()

@router.get("/{company_id}/events", response_model=list[EventOut])
def list_events(company_id: str, db: Session = Depends(get_db)):
    if not db.get(Company, company_id):
        raise HTTPException(status_code=404, detail="Company not found")
    return db.query(ProductEvent).filter_by(company_id=company_id).all()
