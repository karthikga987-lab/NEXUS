# NEXUS DATA_CONTRACT_v1 drift audit

Read-only comparison of `DATA_CONTRACT_v1.md` with the SQLAlchemy entities, Pydantic contracts, and current route responses. No shared fields or database schemas were changed for this audit. The contract itself says it is a draft to verify against the backend.

## Company

| Contract field | SQLAlchemy | Pydantic / endpoint response | Finding |
|---|---|---|---|
| `id` UUID | `Company.id` is `String(36)` UUID text | `CompanyOut.id: str` | Representation is UUID-like text, not a typed UUID. |
| `name` required | Required string column | Create and output require string | Aligned in broad shape. |
| `website` URL optional | Optional `String(500)` | Optional unvalidated string | URL format is not validated. |
| `industry` optional | Optional string column | Omitted from `CompanyCreate` and `CompanyOut` | Stored but not writable/readable through company endpoints. |
| `description` optional | Optional text | Optional create/output string | Aligned. |
| `research_status` enum (`not_started`, `queued`, `running`, `completed`, `partial`, `failed`) | String default is `pending` | Not present in create/output schema | Default is outside the documented enum; current API hides the field. |
| `created_at`, `updated_at` | Both stored | Only `created_at` returned | `updated_at` is not exposed. |

Company collection responses are bare arrays, not the contract's generic `{items, total}` envelope.

## Source

| Contract field | SQLAlchemy | Pydantic / endpoint response | Finding |
|---|---|---|---|
| `id`, `company_id` UUID | String(36), foreign key for company | `SourceOut` strings | UUID format is not schema-validated. |
| `url` required URL | Required string | Required string | No Pydantic URL validation. |
| `title` required | Nullable string | Nullable string | Requiredness mismatch. |
| `publisher` optional | Optional string | Optional string | Aligned. |
| `source_type` enum | String default `other` | String | Enum is not validated. |
| `published_at` | Stored as `publication_date` datetime | `publication_date` in `SourceOut` | Field rename mismatch; contract date is optional, schema permits null. |
| `collected_at` required | Stored | Omitted from `SourceOut` | Not exposed. |
| `content_excerpt` | Stored as full `content_text` | Omitted from `SourceOut` | Name and payload-size semantics differ; raw content is not returned by this route. |
| `content_hash` optional | Stored | Omitted from `SourceOut` | Not exposed. |
| `permission_status` enum | String default `public` | Omitted from `SourceOut` | Critical provenance/access field is not in this response. |
| `reliability` enum | Nullable float score | Omitted from `SourceOut` | Type mismatch (enum vs numeric score) and not exposed. |
| `metadata` | JSON column `metadata` via Python `source_metadata` | Omitted from `SourceOut` | Not exposed. |
| processing state | `processing_status` string, default `pending` | Exposed as `processing_status` | This is an implementation field absent from the contract. |

`GET /api/companies/{id}/sources` returns a bare list, not `{items,total}`.

## Product event

| Contract field | SQLAlchemy | Pydantic / endpoint response | Finding |
|---|---|---|---|
| `id`, `company_id` UUID | String(36), company FK | Strings | UUID format is not validated. |
| `product_name` required | Nullable string | Nullable string | Requiredness mismatch. |
| `event_type` enum | String | String | Enum values are not validated by schema/DB. |
| `title` required | Required string | Required string | Aligned. |
| `description` optional | Optional text | Optional string | Aligned. |
| `event_date` date | Nullable timezone datetime | Nullable datetime | Date vs datetime type mismatch. |
| `stated_reason` optional | Optional text | Optional string | Aligned. |
| `outcome_summary` optional | Stored as `reported_outcome` | `reported_outcome` | Field rename mismatch. |
| `evidence_status` enum | Stored as `evidence_classification` | `evidence_classification` | Field rename mismatch. |
| `extraction_confidence` optional float | Nullable float | Not in `EventOut` | Stored but not exposed by event endpoint. |
| `created_at`, `updated_at` | Both stored | Omitted from `EventOut` | Not exposed. |
| Event-source mapping | `event_sources` many-to-many | `source_ids: list[str]` assembled by route | Relationship is relational; response includes source IDs. |

`GET /api/companies/{id}/events` returns a bare list, not `{items,total}`.

## Relationship

| Contract field | SQLAlchemy | Pydantic / endpoint response | Finding |
|---|---|---|---|
| `id`, company/event IDs | String(36), actual FKs | No shared relationship response schema | Database links exist. |
| `relationship_type` | Python attribute maps to DB `relation_type` | Graph output uses implementation serialization | DB column is legacy-named; allowed values are not DB constrained. |
| `evidence_status` | Python attribute maps to DB `evidence_classification` | Graph output uses implementation serialization | Field name differs in physical DB. |
| `explanation`, `confidence`, `created_at` | Stored; confidence has range check | No dedicated Pydantic contract | Confidence check must survive migrations. |
| relationship source provenance | `relationship_sources` join table with quote/method | Exposed through graph serialization | Additional implementation detail, not specified by v1. |

## Customer feedback

| Contract field | SQLAlchemy | Pydantic / endpoint response | Finding |
|---|---|---|---|
| `id`, `company_id` UUID | String(36), company FK | `company_id: str`; output is partial | UUID format not validated. |
| `product_name`, `source_id`, `source_url`, `external_reference` | Stored | Request supports product and URL only; route does not set `source_id` or `external_reference` | Cannot submit two provenance fields through this request. |
| `feedback_text` required | Stored as `feedback_text` | Request calls it `text` | Request field mismatch. |
| `rating` | Nullable float | Float 0–5 | Numeric range is enforced by schema. |
| `language` | Stored | Not accepted by request | Not writable through endpoint. |
| `created_at_source` | Stored as `created_at_source` | Request calls it `feedback_date` | Request field mismatch. |
| `collected_at` | Stored | Generated, not returned on create | Not exposed on create response. |
| `sentiment`, `feedback_type`, `analysis_status` enums | String columns | Analyzer writes values; create response includes sentiment/type but not analysis status | Values are not constrained by DB/Pydantic enum types. |
| `topics` array | Normalized `feedback_topics` join table | Create response returns list; analysis endpoint returns topic counts | Relational storage differs from array representation but is reasonable. |

`POST /api/feedback` returns only `{id,status,sentiment,topics,feedback_type}`. Analysis and trend endpoints are `/api/feedback/analysis/{company_id}` and `/api/feedback/trends/{company_id}`; v1 lists only the company feedback collection endpoint, which is not implemented as documented.

## Proposal analysis

| Contract field | SQLAlchemy | Pydantic / endpoint response | Finding |
|---|---|---|---|
| analysis `id`, `company_id` | Analysis has `id`, `proposal_id`; company is reached through proposal | Create response has `analysis_id` and `proposal_id` | Contract shape does not match normalized storage/output. |
| `proposal_title`, `proposal_text` | Stored on `Proposal.title`, `Proposal.description` | Request requires `title`, `description` | Field names differ. |
| status and timestamps | Analysis stores status/created/completed | Analyze and GET responses expose these | Mostly aligned in concepts. |
| `similar_event_ids`, `related_feedback_ids` | Join tables `analysis_events`, `analysis_feedback` exist | Current finalization does not expose these IDs as contract arrays | Relationship persistence is available, response mapping differs. |
| `evidence` | `AnalysisEvidence` rows store source/event/claim/classification | Analyze returns claims and evidence passage arrays; GET reconstructs claims from persisted rows | Different object shape; verification status and scope are implementation extensions. |
| `risks`, `recommendation`, `limitations` | JSON/text/JSON columns | Returned in analyze and GET responses | Aligned in broad purpose. |
| status enum | String column | String output | No enum enforcement. |

Request path is `POST /api/proposals/analyze`; proposal retrieval is `GET /api/proposals/{analysis_id}`. The v1 example uses `proposal_title` and `proposal_text`, while the current request schema uses `title` and `description`.

## Endpoint-level mismatches

- Health is `GET /health`, while v1 lists `GET /api/health`.
- Research is `POST /api/companies/{id}/research?max_pages=...`; v1 shows a JSON `{refresh: false}` body.
- Ingestion is exposed under `/api/ingestion/companies/{id}/process` and `/status`; v1 does not list those endpoints.
- Collection routes return arrays rather than the documented `{items,total}` shape.
- The older `docs/API_CONTRACT.md` documents v0.1 placeholder behavior and older names; it is not consistent with the current implementation or v1 contract.

## Recommended coordinated resolution

1. Treat v1 as the negotiation baseline, but confirm which names the frontend and all four members already consume before freezing it.
2. Agree on one canonical field map, especially status enums, source content/provenance, event outcome/evidence naming, feedback request names, and proposal request/output shape.
3. Prefer API/schema adapters for compatibility first. Keep existing physical columns and accept/emit aliases during a deprecation window where feasible.
4. If physical storage changes are needed, create an additive forward migration with a data backfill and explicit rollback limits. Do not edit or run destructive migrations against user databases as part of this audit.
5. Update the API contract, generated OpenAPI expectations, frontend client/types, and integration fixtures in one coordinated change. Add contract tests before changing payloads.
