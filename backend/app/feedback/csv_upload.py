
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Company, Feedback
from app.models.entities import feedback_topics
from app.feedback.analyzer import analyze_feedback


router = APIRouter()

MAX_CSV_SIZE = 5 * 1024 * 1024  # 5 MB


def _normalize_text(value: str | None) -> str:
    """Normalize text for duplicate comparison."""
    return " ".join((value or "").split()).casefold()


def _duplicate_key(feedback_text: str, source_url: str | None) -> tuple:
    return (
        _normalize_text(feedback_text),
        _normalize_text(source_url),
    )


@router.post("/upload-csv")
async def upload_csv(
    company_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        if db.get(Company, company_id) is None:
            raise HTTPException(
                status_code=404,
                detail="Company not found",
            )

        if not (file.filename or "").lower().endswith(".csv"):
            raise HTTPException(
                status_code=400,
                detail="Please upload a CSV file",
            )

        content = await file.read(MAX_CSV_SIZE + 1)

        if len(content) > MAX_CSV_SIZE:
            raise HTTPException(
                status_code=413,
                detail="CSV file exceeds the 5 MB limit",
            )

        try:
            decoded = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise HTTPException(
                status_code=400,
                detail="CSV must use UTF-8 encoding",
            )

        reader = csv.DictReader(io.StringIO(decoded))

        if not reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="CSV file is empty or missing headers",
            )

        reader.fieldnames = [
            (name or "").strip().lower()
            for name in reader.fieldnames
        ]

        if "text" not in reader.fieldnames:
            raise HTTPException(
                status_code=400,
                detail="CSV must contain a text column",
            )

        # Load existing feedback keys for this company.
        existing_records = (
            db.query(Feedback.feedback_text, Feedback.source_url)
            .filter(Feedback.company_id == company_id)
            .all()
        )

        existing_keys = {
            _duplicate_key(text, source_url)
            for text, source_url in existing_records
        }

        # Also catches duplicates appearing within this CSV.
        seen_keys = set(existing_keys)

        stored = 0
        skipped_duplicates = 0
        errors = []

        try:
            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    errors.append({
                        "row": row_number,
                        "error": "Unexpected extra CSV columns",
                    })
                    continue

                feedback_text = (row.get("text") or "").strip()

                if not feedback_text:
                    errors.append({
                        "row": row_number,
                        "error": "Empty feedback",
                    })
                    continue

                source_url = (
                    (row.get("source_url") or "").strip() or None
                )

                duplicate_key = _duplicate_key(
                    feedback_text,
                    source_url,
                )

                if duplicate_key in seen_keys:
                    skipped_duplicates += 1
                    continue

                rating = None
                raw_rating = (row.get("rating") or "").strip()

                if raw_rating:
                    try:
                        rating = float(raw_rating)

                        if not 0 <= rating <= 5:
                            raise ValueError
                    except ValueError:
                        errors.append({
                            "row": row_number,
                            "error": "Rating must be between 0 and 5",
                        })
                        continue

                feedback_date = None
                raw_date = (
                    row.get("feedback_date")
                    or row.get("created_at_source")
                    or ""
                ).strip()

                if raw_date:
                    try:
                        feedback_date = datetime.fromisoformat(
                            raw_date.replace("Z", "+00:00")
                        )

                        if feedback_date.tzinfo is None:
                            feedback_date = feedback_date.replace(
                                tzinfo=timezone.utc
                            )
                    except ValueError:
                        errors.append({
                            "row": row_number,
                            "error": "Invalid feedback_date; use ISO 8601",
                        })
                        continue

                analysis = analyze_feedback(feedback_text)

                item = Feedback(
                    company_id=company_id,
                    feedback_text=feedback_text,
                    product_name=(
                        (row.get("product_name") or "").strip() or None
                    ),
                    source_url=source_url,
                    rating=rating,
                    created_at_source=feedback_date,
                    sentiment=analysis["sentiment"],
                    feedback_type=analysis["feedback_type"],
                    analysis_status="completed",
                )

                db.add(item)
                db.flush()

                for topic in analysis["topics"]:
                    db.execute(
                        feedback_topics.insert().values(
                            feedback_id=item.id,
                            topic=topic,
                        )
                    )

                seen_keys.add(duplicate_key)
                stored += 1

            db.commit()

        except Exception:
            db.rollback()
            raise

        return {
            "message": "CSV processing completed",
            "company_id": company_id,
            "stored": stored,
            "skipped_duplicates": skipped_duplicates,
            "failed": len(errors),
            "errors": errors,
        }

    except csv.Error:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Invalid CSV format",
        )

    finally:
        await file.close()
