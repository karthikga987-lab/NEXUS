# Shared API Contract (v0.1)

Base URL: `http://127.0.0.1:8000`

## Create company
`POST /api/companies`

```json
{
  "name": "Example Company",
  "website": "https://example.com",
  "description": "Optional description"
}
```

Returns a company object with a UUID `id`. Use this exact ID in all later requests.

## Start research
`POST /api/companies/{company_id}/research`

Currently returns `status: not_implemented`. Member 2 owns implementation.

## List sources and events
- `GET /api/companies/{company_id}/sources`
- `GET /api/companies/{company_id}/events`

All source and event records must retain provenance. `ProductEvent.source_ids` is an array of source document UUIDs.

## Analyze proposal
`POST /api/proposals/analyze`

```json
{
  "company_id": "UUID_FROM_CREATE_COMPANY",
  "title": "Improve onboarding",
  "description": "A sufficiently detailed description of the proposed product change..."
}
```

Currently stores a proposal and returns a placeholder status. Member 3 owns implementation. Do not display placeholder responses as AI conclusions.

## Add feedback
`POST /api/feedback`

```json
{
  "company_id": "UUID_FROM_CREATE_COMPANY",
  "product_name": "Example Product",
  "text": "The onboarding process is confusing.",
  "source_url": "https://example.com/review",
  "source_type": "public_review",
  "rating": 2.0,
  "feedback_date": "2026-01-15T10:00:00Z"
}
```

## Evidence classifications

Use exactly:
- `documented_cause`
- `supported_relationship`
- `correlation`
- `unknown`

## Relationship types

Use exactly:
- `PRECEDED_BY`
- `MOTIVATED_BY`
- `APPROVED_BY`
- `TESTED_THROUGH`
- `RESULTED_IN`
- `RECEIVED_FEEDBACK`
- `CHANGED_BECAUSE_OF`

Discuss additions before changing these shared enums/contracts.
