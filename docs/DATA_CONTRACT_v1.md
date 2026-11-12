

\# NEXUS – Shared Data Contract v1.0



\## 1. Global Conventions



\- Database: PostgreSQL

\- Primary keys: UUID

\- API format: JSON

\- Field naming: snake\_case

\- Date/time: ISO 8601 UTC

\- Missing or unknown values: null

\- Every extracted event must have source evidence.

\- Never invent dates, decisions, reasons, metrics or outcomes.

\- Sequence does not automatically prove causation.



\---



\## 2. COMPANY



\### Fields



| Field | Type | Required |

|---|---|---|

| id | UUID | Yes |

| name | String | Yes |

| website | URL | No |

| industry | String | No |

| description | String | No |

| research\_status | Enum | Yes |

| created\_at | Datetime | Yes |

| updated\_at | Datetime | Yes |



\### Allowed values – research\_status



\- not\_started

\- queued

\- running

\- completed

\- partial

\- failed



\### Example



{

&#x20; "id": "uuid",

&#x20; "name": "Google",

&#x20; "website": "https://google.com",

&#x20; "industry": "Technology",

&#x20; "description": null,

&#x20; "research\_status": "completed",

&#x20; "created\_at": "2026-11-08T12:30:00Z",

&#x20; "updated\_at": "2026-11-08T12:30:00Z"

}



\---



\## 3. SOURCE



\### Fields



| Field | Type | Required |

|---|---|---|

| id | UUID | Yes |

| company\_id | UUID | Yes |

| url | URL | Yes |

| title | String | Yes |

| publisher | String | No |

| source\_type | Enum | Yes |

| published\_at | Datetime | No |

| collected\_at | Datetime | Yes |

| content\_excerpt | Text | No |

| content\_hash | String | No |

| permission\_status | Enum | Yes |

| reliability | Enum | Yes |

| metadata | JSON | No |



\### Allowed values – source\_type



\- official\_blog

\- press\_release

\- annual\_report

\- investor\_presentation

\- release\_notes

\- engineering\_blog

\- interview

\- news

\- regulatory\_filing

\- app\_review

\- forum

\- internal\_document

\- other



\### Allowed values – permission\_status



\- public

\- authorized\_internal

\- restricted

\- unknown



\### Allowed values – reliability



\- primary

\- reputable\_secondary

\- user\_generated

\- unknown



\### Example



{

&#x20; "id": "uuid",

&#x20; "company\_id": "uuid",

&#x20; "url": "https://example.com/product-update",

&#x20; "title": "Product Update",

&#x20; "publisher": "Example Company",

&#x20; "source\_type": "official\_blog",

&#x20; "published\_at": "2025-06-10T00:00:00Z",

&#x20; "collected\_at": "2026-11-08T12:30:00Z",

&#x20; "content\_excerpt": "Original relevant text...",

&#x20; "content\_hash": "sha256:...",

&#x20; "permission\_status": "public",

&#x20; "reliability": "primary",

&#x20; "metadata": {}

}



\---



\## 4. PRODUCT EVENT



\### Fields



| Field | Type | Required |

|---|---|---|

| id | UUID | Yes |

| company\_id | UUID | Yes |

| product\_name | String | Yes |

| event\_type | Enum | Yes |

| title | String | Yes |

| description | Text | No |

| event\_date | Date | No |

| stated\_reason | Text | No |

| outcome\_summary | Text | No |

| evidence\_status | Enum | Yes |

| extraction\_confidence | Float | No |

| created\_at | Datetime | Yes |

| updated\_at | Datetime | Yes |



\### Allowed values – event\_type



\- product\_launch

\- feature\_launch

\- feature\_change

\- feature\_removal

\- pricing\_change

\- experiment

\- strategic\_decision

\- partnership

\- acquisition

\- market\_entry

\- market\_exit

\- incident

\- other



\### Allowed values – evidence\_status



\- documented

\- supported

\- correlation

\- unknown



\### Example



{

&#x20; "id": "uuid",

&#x20; "company\_id": "uuid",

&#x20; "product\_name": "Google Maps",

&#x20; "event\_type": "feature\_launch",

&#x20; "title": "Introduced a new feature",

&#x20; "description": "Description supported by source material",

&#x20; "event\_date": "2025-06-10",

&#x20; "stated\_reason": null,

&#x20; "outcome\_summary": null,

&#x20; "evidence\_status": "documented",

&#x20; "extraction\_confidence": 0.91,

&#x20; "created\_at": "2026-11-08T12:30:00Z",

&#x20; "updated\_at": "2026-11-08T12:30:00Z"

}



\### Event–Source mapping



Each event must link to one or more source IDs through a many-to-many mapping.



\---



\## 5. RELATIONSHIP



\### Fields



| Field | Type | Required |

|---|---|---|

| id | UUID | Yes |

| company\_id | UUID | Yes |

| from\_event\_id | UUID | Yes |

| to\_event\_id | UUID | Yes |

| relationship\_type | Enum | Yes |

| evidence\_status | Enum | Yes |

| explanation | Text | No |

| confidence | Float | No |

| created\_at | Datetime | Yes |



\### Allowed values – relationship\_type



\- PRECEDED\_BY

\- MOTIVATED\_BY

\- APPROVED\_BY

\- TESTED\_THROUGH

\- RESULTED\_IN

\- RECEIVED\_FEEDBACK

\- CHANGED\_BECAUSE\_OF



\### Allowed values – evidence\_status



\- documented\_cause

\- supported\_relationship

\- correlation

\- unknown



\### Example



{

&#x20; "id": "uuid",

&#x20; "company\_id": "uuid",

&#x20; "from\_event\_id": "uuid",

&#x20; "to\_event\_id": "uuid",

&#x20; "relationship\_type": "RESULTED\_IN",

&#x20; "evidence\_status": "supported\_relationship",

&#x20; "explanation": "Evidence-supported connection",

&#x20; "confidence": 0.78,

&#x20; "created\_at": "2026-11-08T12:30:00Z"

}



\### Rule



Never claim that one event caused another just because it happened earlier.



\---



\## 6. CUSTOMER FEEDBACK



\### Fields



| Field | Type | Required |

|---|---|---|

| id | UUID | Yes |

| company\_id | UUID | Yes |

| product\_name | String | No |

| source\_id | UUID | No |

| source\_url | URL | No |

| external\_reference | String | No |

| feedback\_text | Text | Yes |

| rating | Float | No |

| language | String | No |

| created\_at\_source | Datetime | No |

| collected\_at | Datetime | Yes |

| sentiment | Enum | Yes |

| topics | Array of strings | No |

| feedback\_type | Enum | Yes |

| analysis\_status | Enum | Yes |



\### Allowed values – sentiment



\- positive

\- neutral

\- negative

\- mixed

\- unknown



\### Allowed values – feedback\_type



\- complaint

\- feature\_request

\- praise

\- question

\- other



\### Allowed values – analysis\_status



\- pending

\- completed

\- failed



\### Example



{

&#x20; "id": "uuid",

&#x20; "company\_id": "uuid",

&#x20; "product\_name": "Google Maps",

&#x20; "source\_id": "uuid",

&#x20; "source\_url": "https://example.com/review",

&#x20; "external\_reference": null,

&#x20; "feedback\_text": "The original customer feedback",

&#x20; "rating": 3,

&#x20; "language": "en",

&#x20; "created\_at\_source": "2025-06-12T00:00:00Z",

&#x20; "collected\_at": "2026-11-08T12:30:00Z",

&#x20; "sentiment": "negative",

&#x20; "topics": \["navigation", "performance"],

&#x20; "feedback\_type": "complaint",

&#x20; "analysis\_status": "completed"

}



\---



\## 7. PROPOSAL ANALYSIS



\### Fields



| Field | Type | Required |

|---|---|---|

| id | UUID | Yes |

| company\_id | UUID | Yes |

| proposal\_title | String | Yes |

| proposal\_text | Text | Yes |

| status | Enum | Yes |

| similar\_event\_ids | Array of UUIDs | No |

| related\_feedback\_ids | Array of UUIDs | No |

| evidence | Array of objects | No |

| risks | Array of objects | No |

| recommendation | Text | No |

| limitations | Array of strings | No |

| created\_at | Datetime | Yes |

| completed\_at | Datetime | No |



\### Allowed values – status



\- queued

\- running

\- completed

\- partial

\- failed



\### Evidence object



\- source\_id: UUID

\- event\_id: UUID or null

\- claim: String



\### Risk object



\- description: String

\- evidence\_status: documented / inference / unknown

\- supporting\_source\_ids: Array of UUIDs



\### Example



{

&#x20; "id": "uuid",

&#x20; "company\_id": "uuid",

&#x20; "proposal\_title": "Improve onboarding",

&#x20; "proposal\_text": "Description of proposed change",

&#x20; "status": "completed",

&#x20; "similar\_event\_ids": \[],

&#x20; "related\_feedback\_ids": \[],

&#x20; "evidence": \[],

&#x20; "risks": \[],

&#x20; "recommendation": "Evidence-based recommendation",

&#x20; "limitations": \["No internal experiment metrics available."],

&#x20; "created\_at": "2026-11-08T12:30:00Z",

&#x20; "completed\_at": "2026-11-08T12:31:00Z"

}



\---



\## 8. DATABASE RELATIONSHIPS



\- Company → Sources: One-to-Many

\- Company → Product Events: One-to-Many

\- Company → Feedback: One-to-Many

\- Company → Relationships: One-to-Many

\- Company → Proposal Analyses: One-to-Many

\- Sources ↔ Product Events: Many-to-Many

\- Product Events ↔ Relationships: Through event IDs

\- Sources → Feedback: One-to-Many or optional

\- Product Events ↔ Proposal Analyses: Many-to-Many

\- Feedback ↔ Proposal Analyses: Many-to-Many



IMPORTANT:

Use actual foreign keys and join tables in the relational database. Arrays of UUIDs in API responses are representations, not substitutes for relational constraints.



\---



\## 9. API ENDPOINT CONTRACT



Base prefix: /api



\### Companies

\- POST /api/companies

\- GET /api/companies

\- GET /api/companies/{company\_id}



\### Research

\- POST /api/companies/{company\_id}/research



\### Sources

\- GET /api/companies/{company\_id}/sources



\### Events

\- GET /api/companies/{company\_id}/events



\### Proposals

\- POST /api/proposals/analyze

\- GET /api/proposals/{analysis\_id}



\### Feedback

\- POST /api/feedback

\- GET /api/companies/{company\_id}/feedback



\### Health

\- GET /api/health



\---



\## 10. API REQUEST EXAMPLES



\### Create Company



{

&#x20; "name": "Google",

&#x20; "website": "https://google.com",

&#x20; "industry": "Technology"

}



\### Start Research



{

&#x20; "refresh": false

}



\### Analyze Proposal



{

&#x20; "company\_id": "uuid",

&#x20; "proposal\_title": "Improve onboarding",

&#x20; "proposal\_text": "We propose simplifying the onboarding flow."

}



\### Submit Feedback



{

&#x20; "company\_id": "uuid",

&#x20; "product\_name": "Example Product",

&#x20; "source\_url": "https://example.com/review/123",

&#x20; "feedback\_text": "The exact feedback text...",

&#x20; "rating": 3,

&#x20; "created\_at\_source": "2025-06-12T00:00:00Z"

}



\---



\## 11. STANDARD API RESPONSES



\### Collection response



{

&#x20; "items": \[],

&#x20; "total": 0

}



\### Error response



{

&#x20; "detail": {

&#x20;   "code": "VALIDATION\_ERROR",

&#x20;   "message": "company\_id is required"

&#x20; }

}



\### HTTP status codes



\- 200: Success

\- 201: Created

\- 202: Accepted / queued

\- 400: Bad request

\- 401: Unauthorized

\- 403: Forbidden

\- 404: Not found

\- 409: Conflict

\- 422: Validation error

\- 500: Internal server error



\---



\## 12. EVIDENCE RULES



1\. Every extracted event must reference at least one source.

2\. Preserve original source URLs and relevant excerpts.

3\. Keep publication date separate from actual event date.

4\. Record reasons only when explicitly stated by a source.

5\. Do not invent private company information.

6\. Distinguish documented facts from supported relationships and correlations.

7\. Confidence measures extraction certainty, not causal truth.

8\. Preserve raw customer feedback.

9\. Mark unavailable internal metrics as unavailable.

10\. Recommendations must include supporting evidence and limitations.



\---



\## 13. TEAM IMPLEMENTATION RULES



\### Member 1 – Frontend

Use the API request/response structures and enum values exactly.



\### Member 2 – Data Collection \& Database

Implement Company, Source, Product Event models and source mappings.



\### Member 3 – AI \& Decision Intelligence

Implement extraction, evidence validation, relationships, embeddings, RAG and proposal analysis.



\### Member 4 – Customer Intelligence

Implement feedback ingestion, sentiment, topics, feedback analysis and event links.



\### ALL MEMBERS

\- Do not rename shared fields.

\- Do not invent new enum values.

\- Discuss schema changes before implementing them.

\- Use UUIDs for IDs.

\- Use ISO 8601 UTC for timestamps.

\- Preserve evidence and provenance.

\- Coordinate changes through GitHub Pull Requests.



\---



NEXUS DATA CONTRACT v1.0

Status: Draft – verify against backend before freezing.




## Additive v1 Extension: Knowledge Items and Research Runs

This backward-compatible extension leaves every existing v1 entity, field, endpoint, and enum unchanged. It adds two new records required for evidence-linked non-event knowledge and persisted research statistics. Migration `d4e6c8a109bf` creates only these tables.

### KnowledgeItem

| Field | Type | Required |
|---|---|---|
| id | UUID | Yes |
| company_id | UUID | Yes |
| source_id | UUID (Source.id) | Yes |
| item_type | Enum | Yes |
| title | String | Yes |
| description | Text | Yes |
| subject_name | String | No |
| actor | String | No |
| status | Enum | Yes |
| item_date | Datetime UTC | No |
| evidence_quote | Text, exact source excerpt | Yes |
| evidence_classification | Existing evidence classification | Yes |
| extraction_confidence | Float from 0 to 1 | No |
| created_at | Datetime UTC | Yes |
| collected_at | Datetime UTC | Yes |

Allowed `item_type` values: `proposal`, `decision`, `concern`, `feedback`, `action_item`, `outcome`.

Allowed `status` values: `proposed`, `approved`, `rejected`, `deferred`, `in_progress`, `completed`, `open`, `resolved`, `unknown`.

A KnowledgeItem supplements ProductEvent and does not replace or duplicate event extraction. Every item points to the existing Source record and must retain an exact quotation present in that source. `item_date` is null unless an exact source date quotation supports it.

### Authorized local document representation

Internal text documents use the existing Source entity with `source_type=internal_document` and `permission_status=authorized_internal`. Their `url` value is an opaque `internal://` reference, not a public web link. Original filename, author/date metadata, synthetic label, and evidence origin are stored in the existing Source metadata JSON. Only `.txt` and `.md` uploads are supported by this implementation. Internal source APIs and AI retrieval require explicit local-development enablement and a loopback request; they are not production-secure without authentication and authorization.

### ResearchRun

A ResearchRun stores per-company research status, start/completion timestamps, summary counts, and a safe failure summary. It does not store fetched page bodies or search-result snippets. `counts` are JSON for the bounded run and do not add enum values to the existing Company contract.

Downgrade refuses to drop either table while rows exist, preventing accidental loss of KnowledgeItem or research-run data.

### Additive source API provenance fields

The existing `GET /api/companies/{company_id}/sources` response retains all prior fields. Optional response fields expose the original discovered URL, a bounded content excerpt, source classification/origin, permission status, collection timestamp, content kind, discovery method, and exact event quotations already stored in Source metadata. `event_date` is returned only when exactly one linked extracted event has a documented date; otherwise it is null. Extraction confidence is an AI estimate and does not establish truth. These response-only fields do not add or alter Source table columns.
