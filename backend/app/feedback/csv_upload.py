
import csv
import io

from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company, Feedback
from app.feedback.analyzer import analyze_feedback

router = APIRouter()


@router.post("/upload-csv")
async def upload_csv(
    company_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # Check company
    if not db.get(Company, company_id):
        raise HTTPException(
            status_code=404,
            detail="Company not found"
        )

    # Check file type
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a CSV file"
        )

    content = await file.read()

    try:
        reader = csv.DictReader(
            io.StringIO(content.decode("utf-8-sig"))
        )

        # Check required column
        if not reader.fieldnames or "text" not in reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="CSV must contain a text column"
            )

        stored = 0
        errors = []

        for row_number, row in enumerate(reader, start=2):

            feedback_text = (row.get("text") or "").strip()

            # Check empty feedback
            if not feedback_text:
                errors.append({
                    "row": row_number,
                    "error": "Empty feedback"
                })
                continue

            # Validate rating
            rating = None

            if row.get("rating"):
                try:
                    rating = float(row["rating"])

                    if not 0 <= rating <= 5:
                        raise ValueError()

                except ValueError:
                    errors.append({
                        "row": row_number,
                        "error": "Rating must be between 0 and 5"
                    })
                    continue

            # Analyse feedback
            analysis = analyze_feedback(feedback_text)

            # Store valid feedback
            item = Feedback(
                company_id=company_id,
                text=feedback_text,
                product_name=row.get("product_name") or None,
                source_url=row.get("source_url") or None,
                rating=rating,
                sentiment=analysis["sentiment"],
                topic=analysis["topic"],
                source_type="csv_upload"
            )

            db.add(item)
            stored += 1

        db.commit()

        return {
            "message": "CSV processed successfully",
            "stored": stored,
            "failed": len(errors),
            "errors": errors
        }

    except UnicodeDecodeError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="CSV must use UTF-8 encoding"
        )

    except Exception:
        db.rollback()
        raise
