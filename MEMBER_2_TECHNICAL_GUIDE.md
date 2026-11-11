# NEXUS Member 2 Technical Guide

This guide describes the source research and evidence pipeline in the current NEXUS backend. It is written against the code in `backend/app`; it does not describe Member 3’s retrieval or answer-generation work as if it already exists.

## 1. What Member 2 owns

Member 2 collects public and imported internal sources, cleans and stores their content, extracts structured events and knowledge with Gemini, and preserves the path from each extracted record back to its evidence. Member 3 can use these records for later retrieval, ranking, and RAG.

```mermaid
flowchart TD
    A[POST /api/companies/{id}/research] --> B[discovery.py]
    B --> C{Candidate URL}
    C --> D[fetcher.py: robots check and HTTP request]
    D -->|Readable HTML| E[processor.py: title and text]
    D -->|Useful search title/snippet only| F[Store as search_snippet]
    D -->|Blocked or failed| G[Store failure reason and retry window]
    E --> H[persistence.py: normalized URL and content hash]
    F --> H
    I[POST /api/companies/{id}/internal-sources] --> J[InternalSource upsert]
    H --> K[SourceDocument]
    J --> L[POST /api/companies/{id}/extract-events]
    K --> L
    L --> M[event_extracter.py: Gemini structured output]
    M --> N[event_persistence.py: source-scoped upserts]
    N --> O[ProductEvent + KnowledgeItem + source references]
    O --> P[Member 3 retrieval and ranking]
```

## 2. Project structure and module roles

```text
backend/app/
  api/routes/companies.py       HTTP endpoints and orchestration
  core/config.py                environment and .env settings
  db/session.py                 SQLAlchemy engine and session dependency
  models/entities.py            company, source, event and knowledge tables
  schemas/contracts.py          shared request/response schemas
  research/discovery.py         public search, candidate URL classification
  research/fetcher.py           robots policy, HTTP, redirects and failures
  research/processor.py         HTML title and readable text extraction
  research/url_utils.py         shared URL normalization
  research/persistence.py       public/internal source upserts and hashes
  research/event_extracter.py   Gemini Pydantic output schemas and prompt
  research/event_persistence.py event and knowledge-item persistence
```

Python files are modules. A folder with `__init__.py` is a package, so code imports shared functions using paths such as `from app.research.persistence import save_source`. This keeps fetching, parsing, and database writes in their own modules. `companies.py` is the API coordinator; it calls those modules rather than duplicating their work.

Functions accept arguments and return values. Type hints such as `url: str` and `-> SourceDocument` document expected inputs and outputs. Lists hold multiple search candidates; dictionaries carry their metadata, for example `source_owner_type` and `search_query`. SQLAlchemy model instances are Python objects that correspond to database rows.

Exceptions represent failures. The fetcher returns a `FetchResult` that carries an error and status code so one blocked page does not stop the rest of the research run. Database sessions are yielded by `get_db()` and closed in a `finally` block. FastAPI’s `Depends(get_db)` is dependency injection: FastAPI supplies a session to the endpoint. `@router.get` and `@router.post` are decorators that register functions as HTTP routes.

The current endpoints and network/database calls are synchronous. There is no async job queue; a research POST runs the collection loop before returning. A long run therefore occupies its request worker until it finishes.

## 3. FastAPI endpoints

FastAPI serves HTTP endpoints. `GET` reads data; `POST` creates a company, ingests a source, or starts research/extraction. A path parameter such as `{company_id}` selects a company. Request models validate input before endpoint code runs. The generated interactive API page is Swagger UI at `/docs`.

The app in `app/main.py` mounts company routes under `/api/companies`, so the router itself has no company prefix. Important routes are:

| Route | Purpose |
|---|---|
| `POST /api/companies` | Create a company |
| `GET /api/companies` | List companies |
| `GET /api/companies/{company_id}` | Read a company |
| `PATCH /api/companies/{company_id}` | Update company fields |
| `POST /api/companies/{company_id}/research` | Discover and collect public sources |
| `GET /api/companies/{company_id}/sources` | List public sources (existing list response shape) |
| `GET /api/companies/{company_id}/sources/{source_id}` | Read one public or internal source |
| `POST /api/companies/{company_id}/internal-sources` | Import text with provenance metadata |
| `GET /api/companies/{company_id}/internal-sources` | List imported/internal sources |
| `POST /api/companies/{company_id}/extract-events` | Extract from eligible public and internal sources |
| `GET /api/companies/{company_id}/events` | List product events |
| `GET /api/companies/{company_id}/knowledge-items` | List proposals, decisions, concerns, feedback, actions, and outcomes |
| `GET/POST /api/companies/{company_id}/event-relationships` | Read or add evidence-backed event relationships |
| `GET /api/companies/{company_id}/research-stats` | Collection and extraction counts |

HTTP status codes include `200` for successful reads/actions, `201` for new records, `400` for invalid research setup, `404` for unknown company/source/event IDs, and `422` for invalid request data. A research result uses `partial` or `failed` when pages fail; it does not label an all-failed run as completed.

An internal import example:

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

`source_identifier` is the external system’s stable ID when one exists. Re-importing the same company and identifier updates the row when its content hash changes. If no identifier exists, a normalized source URL can serve as the stable identity. When neither is provided, NEXUS creates a separate source record instead of guessing that two documents are the same.

A typical research response reports full-page and partial outcomes separately (values are illustrative):

```json
{
  "status": "partial",
  "sources_discovered": 12,
  "sources_fetched": 4,
  "sources_saved": 3,
  "sources_updated": 1,
  "sources_skipped": 2,
  "sources_failed": 6,
  "errors": [
    {"url": "https://public.example/article", "error": "403 Client Error", "snippet_saved": true}
  ]
}
```

For each candidate, the API coordinator calls the fetcher. Readable HTML is sent to `process_html()` and then `save_source()` with discovery metadata. A failure is either saved as a clearly marked search snippet or recorded with its failure reason. The loop then continues to the next candidate.

## 4. Public discovery and fetching

`discovery.py` tries the company homepage, common company pages, same-domain links, a sitemap, and six DDGS searches for official updates, news, government filings, partnerships, customer reviews, and industry analysis. Searches run independently: one query failure is logged and the next query still runs. Results carry their URL, title/snippet when available, discovery method, and originating query.

URLs identify web resources. A domain is the host such as `tesla.com`. `normalize_url()` lowercases scheme/host, removes `www`, default ports, fragments, trailing path slashes, and common tracking parameters such as `utm_source`; meaningful query parameters remain. Discovery and persistence call this one shared function so URL identity is consistent.

`classify_source()` labels target-company hosts as official target sources, known regulator/news domains as regulator/news sources, and other hosts as external. The existing authority scale is numeric: 1 official primary, 2 regulatory/authoritative, 3 reputable secondary, and 4 other public sources. A search result alone cannot prove another company owns a page, so “other company official” is not guessed from text.

`DDGS` is the installed free search client. It asks public search backends for results; results can contain a title and snippet as well as a URL. Search snippets are not full pages. If a page fails but the result has enough title/snippet text, NEXUS stores it with `content_kind="search_snippet"`, `source_type="search_result"`, and partial status. Event extraction excludes these records until a full source is fetched, avoiding presenting a short search summary as a complete document.

HTTP is the request/response protocol used to fetch pages. NEXUS sends a descriptive `User-Agent`, a timeout, and an accept header. `200` means success; `403` means forbidden; `404` means not found; `429` means rate limited; `500`-range codes indicate server failures. Redirects are followed manually, and robots permissions are checked at each destination. The app does not bypass login, CAPTCHA, or paywall controls. A robots policy that cannot be read is treated as disallowed (fail closed); robots rules are cached for one hour. Recently failed URLs are skipped for six hours.

## 5. Text processing

HTML is the markup browsers display. `processor.py` uses BeautifulSoup to remove scripts, styles, navigation, headers, footers, sidebars, SVGs, and noscript elements. It preserves headings, paragraphs, and list items with spacing and returns the page title separately. `extract_text()` remains a compatibility wrapper; new code uses `process_html()` to keep title and text together.

Only HTML/XHTML/plain text responses are accepted by the fetcher. Uploaded document files, PDFs, and authenticated connectors are not implemented. Internal imports currently accept already-extracted text; adapters for Slack, email, Notion, Jira, and other accounts require authorized credentials and are future work.

## 6. Database and SQLAlchemy

SQLite stores local data in `backend/nexus.db`; PostgreSQL can be selected with `DATABASE_URL`. A table is a collection of rows, and columns hold fields. The ORM (object-relational mapper) lets Python objects represent those rows. `db.add()` stages an insert; assigning a model attribute changes a row; `db.commit()` persists the transaction; `db.refresh()` reads database values back. `db.delete(row)` would delete a row at commit time, but the research refresh path never calls it.

- `Company.id` is the primary key. `company_id` fields are foreign keys that associate sources/events/knowledge with a company.
- `SourceDocument` holds public URL, publisher/title, content, content hash, owner classification, discovery query, content kind, fetch error, processing state, and timestamps.
- `InternalSource` holds source type, original identifier/URL, title, text, author/date, content hash, synthetic-demo label, and processing state.
- `ProductEvent` holds extracted event details and JSON arrays of `source_ids` and detailed `source_references`.
- `KnowledgeItem` holds an extracted proposal/decision/concern/feedback/action/outcome and its exact source ID.
- `EventRelationship` holds a directed event-to-event relation, relation type, source IDs, explanation, and evidence classification.
- `Proposal` and `Feedback` are shared product tables. The existing proposal/feedback routes remain mounted separately.

JSON columns store lists such as an event’s source IDs. Indexes speed up lookups; they are not the same as unique constraints. No new unique URL index was added: historical URL strings can differ while normalizing to the same URL, so application-level canonical matching is used after checking existing rows. Content hashes are SHA-256 digests of UTF-8 text; equal hashes indicate unchanged text for that source, not that two different URLs are the same source.

`save_source()` matches by company plus normalized URL and updates the existing source if content changes. `save_internal_source()` uses a stable source identifier or URL. `save_events()` queries existing company events and source knowledge once per source; event deduplication is scoped to that source, and knowledge deduplication uses source, item type, normalized description, or exact quotation. Similar content from another source is retained as independent evidence.

The shared URL helper makes the canonicalization steps explicit:

```python
parts = urlsplit(url.strip())
port = parts.port
scheme = parts.scheme.lower()
hostname = (parts.hostname or "").lower().removeprefix("www.")
formatted_host = f"[{hostname}]" if ":" in hostname else hostname
netloc = formatted_host
if port and not (scheme == "http" and port == 80) and not (
    scheme == "https" and port == 443
):
    netloc = f"{formatted_host}:{port}"
query = urlencode([
    (key, value)
    for key, value in parse_qsl(parts.query, keep_blank_values=True)
    if not key.lower().startswith("utm_")
    and key.lower() not in TRACKING_PARAMETERS
])
path = parts.path.rstrip("/")
return urlunsplit((scheme, netloc, path, query, ""))
```

`urlsplit()` separates the address into components. The hostname is lowercased, `www.` is removed, default ports are omitted, and the fragment is omitted when the URL is rebuilt. Tracking query fields are filtered while meaningful query fields remain. The real function also rejects invalid ports and non-HTTP schemes. Both discovery and persistence use this shared function.

Persistence uses the hash as an update check:

```python
content_hash = calculate_hash(text)
existing = find_source_by_url(db, company_id, url)
if existing and existing.content_hash != content_hash:
    existing.content_text = text
    existing.content_hash = content_hash
```

The first line fingerprints this source’s text. The second finds the same company and canonical URL. Changed text updates that row; a different URL remains a separate source even if its text is similar.

Alembic manages schema migrations. `alembic upgrade head` applies incremental changes while preserving rows; do not delete or recreate the database to apply a migration. The current migration adds ingestion/error/hash metadata and marks only records whose title already has the `[SYNTHETIC DEMO]` prefix as synthetic. The migration was applied to the current local database, and existing row counts were checked before and after.

## 7. External and internal source origins

Public pages are discovered and fetched from open URLs. Their origin, owner category, authority level, URL, and search query are retained. If only a search result summary is available, `content_kind` says that it is a snippet.

Internal documents are posted to the internal-source ingestion route. The route preserves the supplied source type, identifier, title, source URL, author, recorded date, and synthetic flag. Existing demo records have titles beginning `[SYNTHETIC DEMO]` and their content also states they are hypothetical; the migration sets their `is_synthetic` field. Extraction receives that flag and a source title/type so the prompt can avoid presenting demo discussion as genuine company communication.

Synthetic demo records are for tests only. NEXUS has no live Slack, Gmail, Notion, Confluence, Jira, Linear, or GitHub private-account integration. The import endpoint is a text ingestion interface, not proof that NEXUS is connected to those services. The starter API currently has no authentication/authorization layer, so the internal import route belongs in a trusted development environment until access controls are added.

## 8. Gemini structured extraction

An LLM (large language model) is software trained to understand and produce language. In NEXUS, Gemini is asked to extract only claims supported by source text. The model name is `gemini-3.6-flash`, configured in `event_extracter.py`; the key comes from `GEMINI_API_KEY` in the environment or `.env`. The client is created on first extraction, so non-AI API routes can start without a Gemini key. An extraction call without a key returns an error for that source rather than failing application import.

The prompt includes company, source type, source title, whether the source is internal, and whether it is synthetic. Pydantic classes (`ExtractedEvent`, `ExtractedKnowledgeItem`, and `EventExtractionResult`) describe allowed structured fields and values. Gemini returns JSON matching those schemas, which is easier to validate than free-form prose. Extraction is not the same as generation: the prompt requests supported facts and exact evidence quotations and instructs the model to retain uncertainty and disagreements.

Events include product, type, title, dates, reason/outcome, actor, evidence quote, status, primary/secondary classification, and confidence. Knowledge items include the six item types, title/description, actor, status, date, exact quote, classification, and confidence. Confidence describes how strongly the source supports the extraction; it is not a probability that the claim is objectively true.

Transient 429/5xx Gemini errors are retried with increasing delays. API keys are not included in the research response; error text is truncated and the configured key is redacted. Gemini live calls were not made during verification to avoid consuming the configured model quota; extraction tests use deterministic mocked structured output.

## 9. Evidence and relationships

An event stores source IDs and source references, and every knowledge item stores one `source_id`. This is the automatic source-to-evidence trace. Two different sources are not merged just because their descriptions look alike. Reprocessing unchanged text is skipped using `extraction_hash`; changed text is sent through extraction again, and previous evidence rows are not deleted.

The existing `EventRelationship` table supports evidence-backed directed relations. `POST /event-relationships` accepts the shared relation names (`PRECEDED_BY`, `MOTIVATED_BY`, `APPROVED_BY`, `TESTED_THROUGH`, `RESULTED_IN`, `RECEIVED_FEEDBACK`, `CHANGED_BECAUSE_OF`), evidence classification, explanation, and source IDs. It validates that both events and sources belong to the company and that the cited source supports at least one of the events. Repeating the same relation adds missing source IDs rather than duplicating the row. The GET endpoint exposes stored relations.

Relationship creation is explicit and evidence-validated; the current Gemini schema does not automatically infer event-to-event links. There is no Product table or generic proposal-to-decision/feedback-to-change relationship table in the existing schema. Those links should be added with Member 3 only when the product team agrees on a shared data contract. Do not treat sequence or correlation as causation.

Example using the synthetic charging-support fixtures: the Slack proposal, meeting decision, and prototype outcome remain three separate `KnowledgeItem` rows with three separate internal source IDs. An event extracted from the meeting retains the meeting ID. A relation may be added only when a source supports the relation and its source ID is provided; the code does not silently join the Slack idea to the outcome because the words are similar.

## 10. Running, testing, and debugging

From PowerShell:

```powershell
cd NEXUS-data\backend
.\.venv\Scripts\Activate.ps1
alembic current
alembic upgrade head
python -m compileall app
python -m unittest test_research -v
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`. Configure `.env` with `DATABASE_URL` if needed and `GEMINI_API_KEY` before running live extraction. Keep secrets out of logs and screenshots.

The focused tests use in-memory SQLite and mock Gemini; they cover source URL deduplication, changed content, unchanged extraction skipping, independent records from separate sources, source preservation, internal upsert, HTML cleanup, classification, HTTP 403 reporting, and redirect robots checks. The live checks also exercised DDGS and a robots-aware fetch of `example.com`. The existing three synthetic records were copied read-only into a temporary in-memory database and processed with a deterministic mock, leaving the original rows untouched.

Live-connectivity observation from 2026-11-12: one DDGS run returned 24 Tesla-related results from 20 hostnames; a later run returned no results for its six queries, so search-backend availability was intermittent. Tesla’s homepage and sitemap returned HTTP 403. Two independent Tesla-related publishers and `example.com` returned HTTP 200 through the robots-aware fetcher. The existing local database had 2 companies, 1 public source, 3 internal sources, 3 events, and 16 knowledge items before the migration; those counts remained unchanged afterward, and all 3 already-labelled synthetic sources were flagged. Gemini itself was not called during tests; its API/quota behavior remains unverified.

Debugging checklist:

1. Run `python -m compileall app` to catch syntax errors.
2. Check `/health` and `/docs` to confirm FastAPI starts and routes are mounted.
3. Check `alembic current`; apply `alembic upgrade head` if the database is behind.
4. For source failures, inspect the research response’s `errors` list and stored `fetch_error`. A 403 means the site refused access; NEXUS does not bypass it. A `robots.txt` error means fetching was stopped to respect the access policy.
5. If a URL appears twice, compare its canonical URL, company ID, and `content_hash`; different meaningful query parameters remain different URLs.
6. For missing AI extraction, verify `GEMINI_API_KEY` is configured and check the per-source extraction error. Do not repeatedly retry 429/5xx errors immediately; built-in retry delays already apply.
7. For duplicate-looking items, compare `source_id` and quotation. Different source IDs remain independent evidence.

Common mistakes include calling the companies router with a duplicated `/companies` prefix (the app already mounts it under `/api/companies`), treating snippets as full source text, omitting stable internal source IDs, committing without `db.commit()`, or classifying a proposed action as an approved decision.

## 11. Member 3 handoff

Member 3 should read public evidence from `SourceDocument`, internal evidence from `InternalSource`, extracted events from `ProductEvent`, extracted knowledge from `KnowledgeItem`, and verified event links from `EventRelationship`. The source records preserve text or an explicitly marked snippet, IDs, titles, URLs/identifiers, type, ownership, authority, discovery query/method, hashes, status, and timestamps. Events and knowledge items carry exact quotations, confidence, statuses, and source identifiers.

Start with `GET /api/companies/{id}/sources`, `GET /api/companies/{id}/internal-sources`, `GET /api/companies/{id}/events`, `GET /api/companies/{id}/knowledge-items`, and `GET /api/companies/{id}/event-relationships`. Source records are the evidence of record. A relation is not causal unless its evidence classification and quoted source support that interpretation.

Member 2 does not implement embeddings, vector storage, retrieval ranking, RAG, or final answer generation. Search result snippets are explicitly distinguishable and excluded from Gemini extraction until full content is fetched. Private integrations require authorized connectors and credentials before they can be described as available.

The current React client is still the starter UI: it creates/list companies and reads existing sources/events, but its research/import/extraction controls are not wired to these new routes. That frontend integration remains with Member 1.

## Glossary

| Term | Meaning in NEXUS |
|---|---|
| API | HTTP interface used by the frontend or another service |
| Candidate | A discovered URL plus its source metadata |
| Content hash | SHA-256 fingerprint used to detect changed source text |
| Dependency injection | FastAPI supplying a database session to an endpoint |
| Evidence quote | Exact source passage supporting an extracted record |
| Foreign key | Column connecting a row to another table’s primary key |
| ORM | Python objects mapped to relational database rows |
| Provenance | Where a source or claim came from and how it was collected |
| Robots.txt | A website policy file describing automated crawler access |
| Search snippet | Short search-engine summary, not the complete webpage |
| Synthetic data | Clearly marked hypothetical demo content, not real company records |
| Transaction | A group of database changes persisted by `commit()` |
