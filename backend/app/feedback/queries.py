from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models import SourceDocument
from app.models.entities import Feedback


def list_public_company_feedback(db: Session, company_id: str) -> list[Feedback]:
    """Return this company's feedback without records tied to non-public sources."""
    return (
        db.query(Feedback)
        .outerjoin(SourceDocument, SourceDocument.id == Feedback.source_id)
        .filter(
            Feedback.company_id == company_id,
            or_(
                Feedback.source_id.is_(None),
                and_(
                    SourceDocument.company_id == company_id,
                    SourceDocument.permission_status == "public",
                ),
            ),
        )
        .order_by(Feedback.collected_at.desc())
        .all()
    )
