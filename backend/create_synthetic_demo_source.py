from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.entities import Company, SourceDocument

COMPANY_NAME = "NEXUS Synthetic Demo"
SOURCE_URL = "https://example.invalid/nexus-synthetic-demo-case-study"

CONTENT = """
SYNTHETIC DEMONSTRATION DOCUMENT.
IMPORTANT: Every company, product, date, experiment and result below is fictional.
This document is created exclusively to test the NEXUS AI ingestion pipeline.
It does not describe actual company history.

Company: NEXUS Synthetic Demo
Product: PulseBoard

EVENT 1 — FICTIONAL PRODUCT LAUNCH

On February 10, 2025, the fictional company launched the PulseBoard beta.
The beta introduced a dashboard that allows users to view project activity
and track task progress in one place.

The stated reason for the launch was to give pilot users a centralized view
of project activity.

EVENT 2 — FICTIONAL PRODUCT EXPERIMENT

On March 3, 2025, the company conducted a fictional two-week experiment
comparing the original PulseBoard dashboard with a redesigned dashboard.

The experiment report stated that 40 fictional pilot users participated.
The report stated that the redesigned dashboard reduced the average time
needed to locate a project update from 90 seconds to 55 seconds.

The report described this as a result of the fictional experiment.
No real customers or production systems were involved.

END OF SYNTHETIC DEMONSTRATION DOCUMENT.
"""

db = SessionLocal()

try:
    company = (
        db.query(Company)
        .filter(Company.name == COMPANY_NAME)
        .first()
    )

    if company is None:
        company = Company(
            name=COMPANY_NAME,
            website=None,
            description=(
                "Synthetic demonstration company. "
                "All associated events and results are fictional."
            ),
        )
        db.add(company)
        db.flush()

    source = (
        db.query(SourceDocument)
        .filter(
            SourceDocument.company_id == company.id,
            SourceDocument.url == SOURCE_URL,
        )
        .first()
    )

    if source is None:
        source = SourceDocument(
            company_id=company.id,
            url=SOURCE_URL,
            title="Synthetic PulseBoard Product Case Study",
            publisher="NEXUS Synthetic Demo Fixture",
            source_type="other",
            content_text=CONTENT,
            # This fully fictional fixture contains no private company data.
            # Keep it retrievable in the isolated, local demo database; the
            # title and body remain explicitly labelled as synthetic.
            permission_status="public",
            processing_status="pending",
            source_metadata={
                "synthetic": True,
                "demo_fixture": True,
                "not_real_company_history": True,
                "created_for": "NEXUS AI pipeline validation",
            },
        )
        db.add(source)
    else:
        source.content_text = CONTENT
        source.permission_status = "public"
        source.processing_status = "pending"
        source.source_metadata = {
            "synthetic": True,
            "demo_fixture": True,
            "not_real_company_history": True,
            "created_for": "NEXUS AI pipeline validation",
        }

    db.commit()

    print("SYNTHETIC DEMO SOURCE CREATED")
    print("Company ID:", company.id)
    print("Company:", company.name)
    print("Source ID:", source.id)
    print("Source status:", source.processing_status)
    print("Synthetic:", source.source_metadata["synthetic"])

except Exception:
    db.rollback()
    raise

finally:
    db.close()
