# NEXUS Final Integration and Hackathon Readiness Report

**Validation date:** 2026-11-12
**Repository:** `C:\Users\KARTHIK G A\Downloads\NEXUS-starter\NEXUS-starter`
**Branch:** `feature/ai-intelligence` at `702dc8a61339c31334b314b0d8a2a313c73344a0`
**Overall assessment:** **PARTIALLY READY** for a supervised, localhost demo using explicitly labelled synthetic data. This pass does not establish production or real-world decision quality.

## Safety and integration decisions

- The working copy was already on `feature/ai-intelligence`, aligned with `origin/feature/ai-intelligence`. Existing tracked edits and untracked team files were preserved. No reset, commit, push, merge, or cherry-pick was performed.
- `origin/feature/data-collection` is at `35e281cef99338d6ea6011d5057f08490809c95c`; this branch differs from the current branch by four and two commits. `origin/main` is three commits behind the current branch.
- Member 2's branch has a separate Alembic ancestry and includes Gemini extraction and schema changes. Merging it would create migration/schema conflicts and a second extraction engine. No branch merge was attempted. The current working copy's research, fetcher, processing, persistence, and related tests remain in place; Ollama/Qwen stays the active extractor.
- This integration adds an append-only extension to `docs/DATA_CONTRACT_v1.md` for `ResearchRun`, `KnowledgeItem`, and source provenance. It does not rename or remove existing contract fields. `backend/app/models/entities.py` and `backend/app/schemas/contracts.py` add the corresponding model/optional response capabilities; the new migration is additive. The existing migration files were not rewritten.
- Member 1's frontend was preserved and extended in place. `frontend/src/App.jsx`, `frontend/src/api/client.js`, and `frontend/src/styles.css` now expose research status, source provenance, knowledge items, and guarded local internal-document import while retaining the existing summary, event, graph, chatbot, feedback, and proposal UI.

## Migration and database status

- Alembic history is connected with one head: `913b86744127 → e02a9b9d1e2e → b7c4e91a2f63 → c8d2f7a1946b → d4e6c8a109bf`.
- Alembic head is `d4e6c8a109bf`. The actual local `backend/nexus.db` remains at `c8d2f7a1946b`; a read-only check during this pass returned `integrity_check=ok`. The new migration has not been applied to that database.
- The pre-upgrade backup at `backend/nexus-backup-20261111T203751Z.db` remains untouched. No actual database was reset, migrated, or otherwise written during this pass.
- That retained backup is at `b7c4e91a2f63`, older than the current database at `c8d2f7a1946b`; create a fresh backup of the current database before any later manual upgrade to `d4e6c8a109bf`.
- The backup and current database have identical row counts: 41 companies, 152 source documents, 20 product events, 25 feedback records, 1,289 embeddings, 0 event relationships, and 0 relationship-source rows. The named relationship confidence constraint is present in the current schema. No invalid stored confidence value was found in the previous read-only check.
- Fresh migration, upgrade from the previous head, confidence acceptance/rejection, invalid legacy-value safety, and safe downgrade are covered using temporary SQLite databases. `backend/tests/test_migration_confidence_constraint.py`: **4 passed**.

## End-to-end validation

The live application smoke test used an isolated temporary SQLite database, the local FastAPI/Vite servers, and locally installed Ollama models. It did not use or reprocess Samsung documents.

The retained local demo database is `backend/nexus-hackathon-demo-20261111T203927Z.db`. It contains the explicitly labelled synthetic source, generated event/embedding, synthetic feedback and proposal, plus public competitor research performed by the proposal endpoint. It is separate from `backend/nexus.db` and is not a production fixture.

| Workflow | Result | Evidence and limits |
|---|---|---|
| Company workspace and summary | **READY** | The compact company summary, counts, empty/missing field labels, and default-collapsed details rendered. This pass also opened/collapsed the detailed view in a localhost browser and verified source metadata, synthetic excerpts, empty event/knowledge states, research counts, and internal-source controls. A narrow-layout smoke check at 200% browser zoom from the earlier pass showed wrapping without visible horizontal overflow; this was not device emulation. |
| Research and source collection | **PARTIALLY READY** | The existing Samsung records were inspected read-only; fresh research was not repeated to avoid duplicate collection. The synthetic company has no website, so the UI correctly disables research for it. The earlier recorded Samsung run reported 12 URLs discovered, 9 documents collected, and 3 fetch failures; those fetch failure causes were not revalidated in this pass. |
| Ingestion and persistence | **PARTIALLY READY** | The labelled synthetic source persisted and processed; the live model extracted/persisted one launch event and produced two 768-dimensional embedding chunks. The same source explicitly contains a second experiment, which the live extraction run missed. This is a measured recall limitation, not evidence that the experiment was absent. |
| RAG and evidence | **PARTIALLY READY** | A live four-part question returned source-linked synthetic evidence for event, date, reason, and outcome, including the documented fictional reduction from 90 seconds to 55 seconds. No unsupported claims were returned. A regression fix prevents the phrase “a result of the experiment” alone from counting as an outcome, and keeps the measured-outcome sentence in RAG candidates. A separate read-only Samsung question returned `insufficient_evidence` with no verified claims, as appropriate for current-product pages that do not document a historical launch, rationale, or outcome. |
| Feedback | **PARTIALLY READY** | A clearly labelled synthetic feedback record was submitted through the UI, persisted, and classified as negative sentiment / usability. It remained available after reload. These are heuristic labels. There is no automatic public-review discovery. |
| Proposal analysis | **PARTIALLY READY** | Earlier live UI request: **197.20 seconds** total (168.46 seconds competitor research, 24.42 seconds model analysis). The initial optimized measurement was 20.60 seconds cold / 11.33 seconds warm. Two additional cold/warm pairs are recorded in the final pre-commit verification below; fresh competitor discovery remains opt-in and eligible stored evidence is used by default. Real-company evidence quality remains unvalidated. |
| Knowledge graph | **PARTIALLY READY** | The synthetic company graph returned 3 nodes and 2 supported links (`HAS_EVENT`, `SUPPORTED_BY`) with no causal edge. The UI presents relationships as a list; it is not a network visualization. |

### Samsung stored evidence

Read-only inspection of the existing Samsung Electronics record (`27b80c9f-9a51-4c73-a60d-6afe4d1b42f4`) found 9 stored sources: 8 processed and 1 failed, 172 embedding chunks, and 0 verified product events. The failed source is “Claim Samsung Business Offers | Samsung Business IN”; persisted metadata records `ingestion_failed_stage=event_extraction` and `Ollama returned an invalid extraction response.` The raw invalid model response was not persisted, so the exact parser/model failure mechanism cannot be determined from the database. The empty event list is not proof that Samsung has no historical product events; the collected pages are mostly company information and current product descriptions.

## Backend and frontend integration checklist

| Capability | Integration status |
|---|---|
| Company create/list/get | Backend routes exist; the frontend creates and lists workspaces. The selected-company workflow uses the list plus company-specific resources. |
| Company research | `POST /api/companies/{id}/research?max_pages=…&search_depth=…` matches the client. DDGS-backed discovery is optional and bounded. A real bounded search was run during the final pre-commit check; it validated candidate discovery only, without fetching or persisting pages. |
| Source, event, and knowledge retrieval | Existing `/sources` and `/events` remain. Added source detail, research stats, and `/knowledge-items` routes. Optional provenance fields are exposed without changing existing fields; knowledge excerpts are returned only with source and exact-quote provenance. |
| Ingestion | Existing `/api/ingestion/companies/{id}/process` remains. Public documents use the same Ollama/Qwen event extraction and embedding pipeline; authorized local internal documents can be explicitly included, with KnowledgeItems persisted alongside events. |
| Feedback | `POST /api/feedback` and `GET /api/feedback/trends/{id}` match the client and were exercised. `GET /api/feedback/analysis/{id}` also exists. The CSV helper module is present, but there is no registered CSV upload route and the frontend has no CSV upload control. |
| Proposal analysis | `POST /api/proposals/analyze` and saved-analysis retrieval remain. The default request reuses eligible stored public evidence and avoids synchronous external crawling; a request can explicitly opt into fresh external research. UI has a cached-evidence default and a fresh-research option. Saved-analysis browsing remains limited. |
| Semantic search and RAG | `POST /api/ai/search` exists but is not exposed in the frontend client. `POST /api/ai/answer` matches the chatbot panel and was exercised. |
| Knowledge graph | Graph and event-relationship endpoints exist. The current frontend renders relationship rows rather than a graph network. |
| Authentication | No API authentication layer is configured. Keep the demo bound to `127.0.0.1`; do not expose the service to an untrusted network. |

## AI and data-quality results

- Ollama was reachable. Installed models: `qwen3:8b`, `nomic-embed-text:latest`, and `llama3.2:3b`. NEXUS is configured for Qwen 3 8B and nomic embeddings; qwen3:4b is not installed and there is no automatic 4B fallback. The live embedding dimension was 768.
- The earlier labelled synthetic evaluation recorded extraction precision **1.0000**, recall **0.8571** (6/7 expected events), synthetic feedback sentiment/type/topic scores **12/12** on 12 examples, and synthetic retrieval macro Precision@3 **0.2667** / Recall@3 **0.8000**. These small fixtures are not population estimates; retrieval precision remains weak.
- The live synthetic long-document run extracted 1 of 2 explicitly stated events. Do not demonstrate complete long-document event recall as established.
- The live Samsung query produced no answerable historical event evidence. No Samsung event was fabricated or inserted.
- Feedback classification remains heuristic and company/user submitted; it is not a public-review crawler and does not establish product events or outcomes.
- Proposal claims and recommendations remain model-generated analysis. The synthetic proposal was explicitly hypothetical; its conservative result is not a company decision or proof of likely success.

## Changes made in the previous readiness continuation

- `backend/app/intelligence/rag.py`: retain long measured-outcome sentences and require an actual outcome or explicit reported absence before marking the outcome aspect supported.
- `backend/tests/test_rag_relevance.py`: cover measured outcome retention, bare “result” wording, and explicit no-outcome reporting.
- `backend/tests/test_workflow_integrations.py`: cover partial-answer status when a verified sentence merely labels something a “result” without documenting an outcome.
- `frontend/src/App.jsx`: key same-source evidence cards by source plus chunk index to remove the live duplicate React key warning.
- `docs/NEXUS_FINAL_HACKATHON_READINESS_REPORT.md`: this handover report.

Earlier changes in this same working-copy task that remain present include `pytest.ini`, `backend/app/api/routes/companies.py`, `backend/app/api/routes/proposals.py`, `backend/app/intelligence/embeddings.py`, `backend/app/knowledge_graph/builder.py`, `backend/app/intelligence/test_embeddings.py`, `backend/tests/test_public_evidence_access.py`, backend/tests/test_rag_relevance.py, and `backend/create_synthetic_demo_source.py`. The already-existing forward migration `backend/migrations/versions/c8d2f7a1946b_restore_relationship_confidence_check.py` and `backend/tests/test_migration_confidence_constraint.py` were preserved and revalidated; they were not rewritten in this integration continuation. Existing Member 1 and other team files were preserved. `frontend/dist` was generated by the build and is ignored by Git.

The Git worktree remains intentionally dirty with existing team files, backups, and evaluation artifacts. This pass did not stage or remove files. See the integration section below for the files changed for this task; the final `git status` still shows branch `feature/ai-intelligence` with no commit or push.

## Final verification

| Command/check | Result |
|---|---:|
| Full backend tests from repository root: `python -m pytest -q -p no:cacheprovider --durations=10` | **198 passed**, 0 failed, 0 skipped; 1 upstream Starlette/anyio deprecation warning; final rerun **13.06 s** |
| Full backend tests from `backend`: `python -m pytest -q -p no:cacheprovider --durations=10` | **198 passed**, 0 failed, 0 skipped; same warning; final rerun **13.67 s**. The earlier 4105.33-second run did not reproduce; its precise cause remains unconfirmed. |
| Competitor cache/isolation regression tests | **8 passed**; verifies cached-discovery behavior and isolates independent test cases |
| Local CORS preflight regression | **2 passed** for `localhost:5173` and `127.0.0.1:5173`; preserves configured non-loopback allowlists |
| Temporary-SQLite migration regression tests | **9 passed** across confidence-constraint and KnowledgeItem migration suites; fresh migration and upgrade path tested |
| Alembic graph | **One connected head:** `d4e6c8a109bf`; actual local DB remains at `c8d2f7a1946b` |
| Frontend production build | **Passed**; Vite 8.3.6, 2,060 modules, final rerun 201 ms |
| Browser smoke | **Passed for `http://localhost:5173`**: API connected, compact view loaded, details expanded and collapsed. A `127.0.0.1` origin initially failed because `.env` listed only `localhost`; the settings fix and both-origin preflight test now cover it. The browser was not rerun after that fix. |
| Local API smoke | **Passed**; `/health` returned `{"status":"ok","service":"nexus-api"}` |
| `git diff --check` | **Passed** |
| Frontend runtime duplicate-key warning | Fixed; no repeat warning appeared in Vite output during the post-fix RAG smoke test |

No failing or skipped tests were reported. No commit, push, merge, cherry-pick, reset, or database deletion was performed.

## Remaining risks and priorities

- **Critical for any network-exposed deployment:** no authentication or authorization layer. For this demo, use localhost only.
- **High:** long-document event recall is incomplete; the Samsung source failure remains; the real Samsung corpus does not currently support a historical-event demo; retrieval precision remains low; automatic customer-review discovery and a registered CSV upload endpoint are absent. DDGS live candidate discovery was verified, but fetching and ingesting live results were not exercised in this final check.
- **Medium:** saved proposal-analysis history is not surfaced as a browse/restore flow; the graph is a relationship list rather than a network; the local access-status wording was corrected after the browser smoke but that exact final text was not rechecked in a browser; this pass did not include full device emulation.
- **Low:** one upstream Starlette/anyio deprecation warning remains.

## Demo setup and runbook

Use a new unique demo database filename; never point the demo at `backend/nexus.db`. In a PowerShell backend terminal:

```powershell
cd "C:\Users\KARTHIK G A\Downloads\NEXUS-starter\NEXUS-starter\backend"
python -m pip install -r requirements.txt
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$demoDb = ".\nexus-demo-$stamp.db"
if (Test-Path $demoDb) { throw "Choose a new demo DB filename; refusing to reuse $demoDb" }
$env:DATABASE_URL = "sqlite:///./nexus-demo-$stamp.db"
$env:NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES = '1' # loopback-only local development feature
python -m alembic upgrade head
python create_synthetic_demo_source.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start Ollama first and verify `ollama list` includes `qwen3:8b` and `nomic-embed-text`; pull either only if missing. In a second PowerShell terminal:

```powershell
cd "C:\Users\KARTHIK G A\Downloads\NEXUS-starter\NEXUS-starter\frontend"
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://localhost:5173` (the default backend CORS origin). Select **NEXUS Synthetic Demo**, process its pending source, and label all source events/results as fictional. A good 5–7 minute flow is summary → expanded source/event evidence → one multi-part RAG question → synthetic feedback. The local synthetic proposal benchmark took 11–21 seconds, but actual timing varies by machine and model load; the UI still does not restore saved analyses after reload. If Ollama or public search is unavailable, show the stored summary, source/event state, feedback theme, and graph links, and say that live RAG/proposal analysis is unavailable. Do not present the Samsung corpus as containing a verified historical product event.

For local internal-source import, keep the backend bound to `127.0.0.1`, set `NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES=1`, and use only authorized documents. This guard is not a substitute for production authentication; do not expose this endpoint on a shared network.

## Member 2 Feature Integration and Proposal Performance

### Integration result

- **DDGS discovery — PARTIALLY READY.** Research discovery now combines official homepage/same-domain/sitemap results with bounded DDGS search categories for products, announcements, press releases, news, regulatory material, and external reporting. Candidates are normalized, deduplicated, relevance-filtered, and fetched through the existing robots-aware URL/SSRF/redirect/content-type protections. Snippets are retained as snippets when full fetching fails; they are excluded from the collected-document count and ingestion. `ddgs>=9.0,<10.0` is declared in `backend/requirements.txt`. DDGS 9.16.1 was installed into the active Python 3.14 environment and a real bounded discovery call completed in 2.88 seconds, returning four candidates without errors. This verified search candidate discovery only, not page fetching, content verification, or persistence. Network-dependent unit tests were corrected to inject an empty searcher explicitly.
- **Internal-source import — PARTIALLY READY.** Local trusted-development endpoints import `.txt` and `.md` documents up to 1 MB, validate UTF-8/text content, preserve filename/author/date and company association, deduplicate imports, and label synthetic documents. Listing and detail routes are available. Access requires the explicit environment switch and a loopback request; there is no production authentication/authorization. The frontend exposes the import and separate processing action. No real private documents were imported.
- **KnowledgeItem — READY in the tested local workflow.** KnowledgeItems complement ProductEvents, preserve company/source IDs, exact source quote, evidence classification, confidence, origin, and timestamps, and are written by the existing Qwen ingestion flow. Retrieval only adds relevant items when the source is already eligible and the exact excerpt exists in source text. They do not create a second extraction engine.
- **Unified research-to-knowledge flow — PARTIALLY READY.** Company research saves eligible documents and provenance; ingestion uses Ollama/Qwen for events and non-event knowledge, verifies quotes, persists results, and creates embeddings. Research stats, source detail, knowledge-item retrieval, event/source evidence, RAG and proposal routes are connected. Temporary-SQLite integration tests cover research/source persistence, internal import through ingestion/embedding/knowledge retrieval, and public/internal evidence scoping. Live DDGS collection and the real Samsung corpus were not rerun.
- **Frontend availability — PARTIALLY READY.** Research controls/status, source detail/provenance, knowledge items, guarded internal import, evidence-scope selection, proposal cached-evidence default, events, graph, feedback, and chatbot are present in the existing frontend. A successful internal-source list request now produces an accurate trusted-local status label instead of the earlier “unavailable until enabled” fallback. The final production build passed. This pass did not perform full manual browser/device testing of each newly added control.

### Proposal performance result

The prior measured baseline was **197.20 seconds** total, including **168.46 seconds** of competitor research and **24.42 seconds** of model analysis. The final implementation defaults to cached eligible public evidence and does not synchronously crawl competitors for every proposal. Fresh external research is an explicit option with a one-hour, bounded in-memory discovery cache. Query embeddings are cached (bounded LRU); retrieval still filters/grounds evidence before generation. The local Qwen model remains the reasoning engine.

Using a labelled synthetic source and temporary SQLite databases with the locally available Qwen 3 8B and nomic embedding model, the initial actual proposal path measured **20.60 seconds cold** and **11.33 seconds warm**. The final repeated measurements were **20.39 / 10.87 seconds** and **13.45 / 10.89 seconds** (cold / warm). In the second pair, Qwen was already resident, so cold refers to a cleared query-embedding cache, not model startup. These measurements meet the under-60-second target on this machine; they are not a real-company quality evaluation or a guarantee for other hardware. No Samsung data or actual development database was used for the benchmark.

### Files changed for this integration and performance pass

- Backend routes and configuration: `backend/app/api/routes/ai.py`, `backend/app/api/routes/companies.py`, `backend/app/api/routes/company_extras.py`, `backend/app/api/routes/ingestion.py`, `backend/app/api/routes/proposals.py`, `backend/app/core/local_access.py`, `backend/app/main.py`, `backend/requirements.txt`.
- Backend settings and regression for the discovered local-origin issue: `backend/app/core/config.py`, `backend/tests/test_cors_origins.py`.
- Research and persistence: `backend/app/research/url_utils.py`, `backend/app/research/discovery.py`, `backend/app/research/service.py`, `backend/app/research/fetcher.py`, `backend/app/research/processor.py`, `backend/app/research/persistence.py`, `backend/app/research/competitors.py`.
- Intelligence, models, and contract: `backend/app/intelligence/embeddings.py`, `backend/app/intelligence/ingestion.py`, `backend/app/intelligence/knowledge_retrieval.py`, `backend/app/intelligence/proposal_analysis.py`, `backend/app/intelligence/rag.py`, `backend/app/models/entities.py`, `backend/app/schemas/contracts.py`, `docs/DATA_CONTRACT_v1.md`, `backend/migrations/versions/d4e6c8a109bf_add_evidence_linked_knowledge_items.py`.
- Frontend: `frontend/src/App.jsx`, `frontend/src/api/client.js`, `frontend/src/styles.css`.
- Regression/integration tests: `backend/tests/test_competitors.py`, `backend/tests/test_competitor_discovery_cache.py`, `backend/tests/test_cors_origins.py`, `backend/tests/test_discovery_pipeline.py`, `backend/tests/test_embedding_query_cache.py`, `backend/tests/test_ingestion_pipeline.py`, `backend/tests/test_internal_sources_api.py`, `backend/tests/test_knowledge_item_migration.py`, `backend/tests/test_knowledge_retrieval.py`, `backend/tests/test_proposal_evidence_scope.py`, `backend/tests/test_research_service.py`, `backend/tests/test_workflow_integrations.py`.

Existing files from the team and earlier work remain in the dirty worktree; this list identifies files touched for the current integration scope and is not a cleanup or staging list. No commit or push was made.

## Final readiness judgment

The integrated application builds and passes the backend suite from both required working directories. The local synthetic workflow demonstrates persistence, one event, embeddings, evidence-grounded RAG, feedback analysis, proposal persistence/analysis, and graph links. It is **PARTIALLY READY** for a supervised synthetic-data demo with manual evidence review. It is **NOT READY** for an unsupervised or network-exposed demo, a claim of complete event extraction, or a real-company historical decision demonstration based on the current Samsung records.

## Historical pre-integration verification snapshot (2026-11-12)

This section records the state before Member 1 frontend recovery and is superseded by the integration results below. Its merge/commit status, test counts, frontend scope, and CSV route statements describe only that earlier point in time.

- **Working tree:** branch `feature/ai-intelligence`, HEAD `702dc8a61339c31334b314b0d8a2a313c73344a0`. Final inspection found 26 modified tracked files and 109 untracked files, with no staged changes. Existing team files, backups, evaluation artifacts, and untracked files were preserved. No stage, commit, push, merge, reset, clean, or delete operation was performed. `git diff --check` passed; Git emitted only LF-to-CRLF normalization warnings for several modified files.
- **DDGS environment and real search:** `ddgs>=9.0,<10.0` is declared in `backend/requirements.txt`. No project virtual environment was present; the active Python 3.14 interpreter now has `ddgs 9.16.1` and `primp 2.0.1`. A bounded real NEXUS discovery call for Unilever used `search_depth=1`, `max_pages=4`, and the configured eight-second DDGS request timeout. It completed in **2.88 seconds**, returned four candidates (the official homepage plus three search candidates), and reported no discovery errors. No result page was fetched or persisted in this check; candidates are leads, not verified evidence. A fresh environment must install `backend/requirements.txt` before using discovery.
- **Pytest duration discrepancy:** root `pytest.ini` configures `testpaths=backend` and `pythonpath=backend`; the configured suite from either repository root or `backend` collects the same 198 tests, including colocated `backend/app/intelligence/test_*.py` tests. `backend/.env` is loaded when running from that directory and contains a database URL, unlike root invocation. Final comparisons overrode `DATABASE_URL` with a separate temporary SQLite file for each run, avoiding the actual development DB. The earlier **4105.33-second** backend run could not be reproduced and its exact cause is unconfirmed; the `.env` difference is a real environment discrepancy, but evidence does not prove it caused that duration. Safe canonical command from either directory: `python -m pytest -q -p no:cacheprovider --durations=10`, with `DATABASE_URL` pointed at a fresh temporary SQLite database. Do not pass only `backend/tests`, because that omits colocated app tests.
- **Network-test isolation fix:** after DDGS was installed, four `test_research_service.py` unit tests began making real discovery calls and failed when extra live candidates appeared. The tests now inject an explicit empty searcher, retaining deterministic test scope while separate discovery tests cover the search behavior. Focused module result: **4 passed in 0.81 seconds**.
- **Full suite:** repository root **198 passed, 0 failed, 0 skipped in 13.06 seconds**; backend directory **198 passed, 0 failed, 0 skipped in 13.67 seconds**. Both runs emitted one upstream Starlette/anyio deprecation warning and used distinct temporary SQLite databases. Neither run pointed at or modified `backend/nexus.db`.
- **Migration:** the revision graph contains five unique connected revisions and one head, `d4e6c8a109bf`. The actual DB remained at `c8d2f7a1946b`, with integrity check `ok`; its recorded modification time did not change. A temporary SQLite backup copy at `c8d2f7a1946b` upgraded successfully to `d4e6c8a109bf`. All 14 pre-existing application tables retained their row counts and content hashes; only the two expected additive tables were created, empty. The relationship confidence check remained present. The migration was not applied to the actual DB. Before a future upgrade, create a fresh backup of the current c8 revision; the older retained backup is at `b7c4e91a2f63`.
- **Proposal timing reproducibility:** the actual proposal route ran four times with local Qwen 3 8B, nomic embeddings, a labelled synthetic source, and temporary SQLite. Pair 1: **20.39 seconds cold / 10.87 seconds warm**. Pair 2: **13.45 seconds cold / 10.89 seconds warm**; Qwen was already resident in pair 2, and only the query-embedding cache was cleared for the cold call. Calls completed using cached-only external evidence with no fresh search. These results are reproducibly under 60 seconds on this machine versus the prior 197.20-second baseline, but do not establish real-company answer quality; cold timing varies with model startup.
- **Frontend and diff:** `npm run build` passed (Vite 8.3.6, 2,060 modules, **201 ms**). `git diff --check` passed. No frontend source changed during this verification pass.
- **Pre-commit recommendation:** ready for a **selective, reviewed commit** of intended source, tests, migrations, and report only. This worktree is not safe for blanket `git add -A`: it contains 109 untracked files, including backups and evaluation/support artifacts. Review and stage explicit paths. Do not apply the migration to the actual local DB until a current-revision backup has been made.

### Remaining pre-commit risks

- The earlier 68-minute pytest run's exact cause remains unresolved, despite both working directories now completing the same configured 198-test suite in about 13 seconds with isolated DB overrides.
- DDGS validation proved bounded search candidate discovery only. Real source fetching, robots decisions, source persistence, and evidence quality from live results remain unverified in this final check.
- The active runtime uses a global Python 3.14 installation rather than a project virtual environment; reproducibility in another environment depends on installing declared requirements there.
- The actual development database intentionally remains at `c8d2f7a1946b`; migration to head is still a release step after backing up the current database.
- Existing product limitations remain: no API authentication, incomplete long-document extraction recall, no automatic review discovery, and no registered CSV upload route.

## Member 1 Frontend Recovery and Backend Integration

### Branch recovery and preservation

- Fetched and integrated `origin/feature/frontend` commit `68d71d2da0100bc34aef9f1dfdf2d18bae7f6edd` (`Build initial NEXUS frontend dashboard`) into `feature/ai-intelligence`. The three overlapping frontend files were manually reconciled with the existing AI dashboard; no force checkout or reset was used.
- Before merging, the 135 then-dirty files were captured outside the repository at `%TEMP%\NEXUS-pre-frontend-snapshot-20261112-072146.zip`; the manifest and SHA-256 checks matched. The original changes are also retained in `stash@{0}`. Unrelated backups, local evaluation artifacts, and untracked team files remain unstaged.
- Member 1's visual direction and page structure were retained. Fabricated sample companies, sources, feedback, graph links, timeline events, canned chatbot responses, and proposal analyses were removed from the connected UI.

### Frontend/API integration

- The company landing page uses the existing health, list, create and detail APIs. The dashboard loads company overview, events, sources, research statistics, KnowledgeItems, graph data, ingestion status and feedback trends/analysis.
- Research and ingestion controls use existing backend routes. Internal document import is shown as trusted-local-only and calls the loopback-guarded API. Feedback submission, chatbot/RAG, proposal analysis, event timeline, source details and graph views use actual API responses.
- The assistant renders answer status, requested-aspect coverage, verified claims and source citations. Proposal analysis renders the returned recommendation, risks, evidence, feedback context and limitations. The graph draws only returned nodes/edges.
- Backend CSV feedback upload exists but is not exposed by the recovered frontend. The UI does not provide a proposal-history list; saved-analysis retrieval exists only by analysis ID. Public graph APIs intentionally omit authorized-internal evidence. No API or shared database contract was changed for the frontend integration.

### Local synthetic API workflow

- A temporary SQLite database was migrated from scratch to `d4e6c8a109bf`; the actual development database was not opened or modified. A labelled synthetic internal Markdown source and labelled synthetic feedback were used.
- **23/23 HTTP checks succeeded** across Vite modules, health/CORS, company create/list/detail, internal import/list, ingestion, event/source/status/KnowledgeItem/graph retrieval, feedback submission/trends/analysis, RAG and proposal analysis. No fresh live research or real-company records were used in this workflow.
- Actual local Ollama/Qwen and nomic embedding services processed the synthetic source: **1 processed, 0 failed, 1 event, 1 KnowledgeItem, 1 embedding chunk**. The proposal analysis API completed in **12.58 seconds** with one eligible evidence passage.
- The first four-part RAG query failed to retrieve a relevant passage. The lexical focus gate treated generic verbs `added` and `measured` as product/topic terms. They were added to the existing query-intent vocabulary with a regression test. The same query then returned `answered_with_verified_evidence`, four claims, and all four requested aspects (event, date, reason, outcome) supported by the synthetic source.

### Final verification and limitations

- Backend suite from the repository root: **199 passed, 0 failed, 0 skipped in 15.70 seconds**. From `backend`: **199 passed, 0 failed, 0 skipped in 15.67 seconds**. Each used a different temporary SQLite database. Each run emitted one upstream Starlette/anyio deprecation warning.
- Frontend `npm run build`: **passed**, Vite 8.3.6, 2,072 modules, **191 ms**.
- `git diff --cached --check`: passed after reviewing the explicit staged file list. No databases, secrets, backups, `node_modules`, or `frontend/dist` files were staged.
- Interactive browser/device click-through was not completed because the computer-use browser tool stopped when it could not establish the active URL. Manual smoke testing of the file picker, responsive layout, chatbot and proposal form remains required before a public demo. Keep the local internal-source endpoint loopback-only; the project does not have production authentication/authorization.
- The live local workflow validates API and model integration with synthetic content; it does not establish real-company extraction quality, fresh research coverage, or production security.

## Latest Member 1 Frontend Update (947138e)

### Review and integration

- Fetched `origin/feature/frontend`; it points to `947138e095f8e578a95784cc70ad0e74acfa58ff`, one commit after the previously integrated frontend commit `68d71d2da0100bc34aef9f1dfdf2d18bae7f6edd`. The upstream change contains 15 frontend files (5,181 insertions, 564 deletions). The integration branch was `feature/ai-intelligence` at `33abd27b34832194e17101597a707c34226c7b0e` before this merge.
- Reviewed the full file list and the changed React components, entry point, styles, and new canvas background. The incoming dashboard/timeline/source/customer/graph/proposal implementations contain illustrative sample records and placeholder “not integrated” states. Those records were not carried into the integrated UI.
- Resolved overlapping changes in `CompanyDashboard.css`, `CustomerIntelligence.jsx`, `KnowledgeGraph.jsx`, `ProductTimeline.jsx`, `ProposalAnalysis.jsx`, `ResearchSources.jsx`, and `styles.css`. The current real API orchestration and response handling were preserved. The updated visual CSS, `CosmicBackground` component, and main entry wrapper were integrated; dynamic summary cards use actual returned counts.

### API compatibility

- The company dashboard still uses the existing company detail, events, sources, research statistics, ingestion status, feedback analysis/trends, KnowledgeItems, graph, research, ingestion, and internal-source routes.
- The source page retains research, ingestion, source provenance, and loopback-guarded local document import. The timeline uses returned ProductEvents and linked source references. Feedback analytics use actual feedback trends/distributions, with heuristic limitations disclosed. The graph renders only API-returned nodes/edges and retains edge provenance details. Proposal analysis still submits through the existing proposal API and shows returned evidence, claims, feedback context, risks and limitations. The assistant/RAG and API base URL were not changed.
- No backend route, API contract, shared data contract, ORM schema, migration, or database was changed in this integration.

### Verification

- Backend root suite: **199 passed, 0 failed, 0 skipped in 16.42 seconds**. Backend-directory suite: **199 passed, 0 failed, 0 skipped in 16.42 seconds**. Each used a separate temporary SQLite URL; each emitted the same upstream Starlette/anyio deprecation warning.
- Frontend production build: **passed**, Vite 8.3.6, 2,079 modules, **203 ms**.
- API health: `GET /health` returned **200** (`status=ok`). CORS preflight for `http://127.0.0.1:5173` returned **200** with the matching allow-origin.
- Direct Vite HTTP check: **11/11** paths returned HTTP 200, covering the page, main entry, App, styles, cosmic background, dashboard, and all six connected feature pages.
- `frontend/package.json` provides `dev`, `build`, and `preview` only; no lint or typecheck script is configured. Playwright/Puppeteer and Chrome/Edge command-line browsers were unavailable in the environment.
- No interactive or headless browser click-through is claimed. Manual visual/responsive smoke testing remains outstanding.
- A pre-fetch SHA-256 manifest recorded the 67 preexisting untracked paths. After integration all 67 paths and file SHA-256 values matched; they remain unstaged. No backup/evaluation artifacts, databases, secrets, `node_modules`, or `frontend/dist` output are staged.

### Remaining demo limitations

The UI uses real backend responses but this pass did not run live company research or model inference. The previous local synthetic workflow remains the evidence for those paths. CSV feedback upload remains backend-only in the UI; proposal history has no list page; internal-source routes remain loopback-only development functionality without production authentication. Readiness remains **PARTIALLY READY** until a manual browser smoke test and supervised local demo are completed.
