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

`GET /api/companies` lists companies, `GET /api/companies/{company_id}` reads one company, and `PATCH /api/companies/{company_id}` updates supplied company fields.

## Start external research
`POST /api/companies/{company_id}/research`

Runs synchronously. The response reports `sources_discovered`, `sources_fetched`, `sources_saved`, `sources_updated`, `sources_skipped`, `sources_failed`, `source_categories`, and per-URL errors. Status is `completed`, `partial`, or `failed`. A saved search summary is marked with `content_kind: search_snippet`; it is not represented as a full webpage.

## List sources and events
- `GET /api/companies/{company_id}/sources`
- `GET /api/companies/{company_id}/events`

These existing routes continue to return lists. Public source rows use `SourceDocument`; event rows retain `source_ids` and detailed `source_references`.

## Import internal source text
`POST /api/companies/{company_id}/internal-sources`

```json
{
  "source_type": "meeting_transcript",
  "source_identifier": "meeting:2026-04-12:review",
  "title": "Quarterly review transcript",
  "content_text": "The team approved a limited prototype test.",
  "author": "Product team",
  "recorded_at": "2026-04-12T10:00:00Z",
  "is_synthetic": false
}
```

Use a stable `source_identifier` from the source system when available. Re-importing the same identifier for the same company updates its text when its SHA-256 content hash changes. `GET /api/companies/{company_id}/internal-sources` lists internal records. This is a text import API; it does not establish a live connection to Slack or another private service.

## Extract and read structured knowledge
- `POST /api/companies/{company_id}/extract-events`
- `GET /api/companies/{company_id}/knowledge-items`

Extraction processes full public pages and internal sources through the shared Gemini path. Search snippets are excluded until full text is collected. Reprocessing an unchanged source is skipped by its extraction hash.

## Event relationships
- `GET /api/companies/{company_id}/event-relationships`
- `POST /api/companies/{company_id}/event-relationships`

Relationship writes require two events, a source owned by that company that supports at least one event, a relation type from the shared list below, and an evidence classification. Repeating a relation adds provenance without duplicating the relationship row.

## Research statistics
`GET /api/companies/{company_id}/research-stats`

Returns public full-page/snippet/failure counts, internal-source count, extraction-complete/pending counts, event count, knowledge-item count, and relationship count.

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
