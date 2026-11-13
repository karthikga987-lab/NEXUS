# NEXUS End-to-End Audit and Real-Company Validation

**Audit date:** 2026-11-12
**Branch / HEAD:** `feature/ai-intelligence` / `ee1e9b5f68cb249486fedafd89058481efbb4177`
**Scope:** Existing implementation, isolated SQLite workflows, real public Microsoft source, regression fixes. No commit or push was made.

## Executive summary

NEXUS starts, passes its backend suite from both supported working directories, builds its frontend, and can collect public pages, persist embeddings, answer a source-grounded question, submit and analyze feedback, and save proposal analysis. The real-company run also found significant limits: the six collected pages were mostly indexes, a relevant 15,225-character article failed structured extraction after Ollama truncated both attempts, and no product events or KnowledgeItems were produced. The knowledge graph therefore contained no relationships. The real sample is too small to establish event-extraction accuracy or broad AI reliability.

Three small reproducible defects were fixed and regression-tested:

1. RAG source diversification could omit a lower-ranked passage containing an explicitly requested result. It now prefers deferred same-source passages that cover a missing question aspect. A live Qwen answer then cited both the pilot passage and the reported attendance metric while leaving the exact launch date unknown.
2. Saved proposal retrieval labelled public same-company sources as `internal`. It now returns the existing `public_company` scope for these citations.

A synthetic API feedback test also reproduced “leaks” being classified as neutral. The lightweight classifier now recognizes leak variants as negative reliability feedback. This improves that specific case; it is not a general sentiment model.

**Readiness: PARTIAL.** The backend/API path is suitable for a supervised local demo with prepared evidence. Do not present the Microsoft corpus as verified product history, and complete a manual browser pass before relying on the UI in a live demo.

## Safety and environment

- Read `docs/DATA_CONTRACT_v1.md`; it and all ORM models were left unchanged. No migration file was modified.
- The actual `backend/nexus.db` was opened read-only to inspect its Alembic revision: `c8d2f7a1946b`. No rows or schema were changed.
- Alembic has one connected head, `d4e6c8a109bf`; history is `913b86744127 → e02a9b9d1e2e → b7c4e91a2f63 → c8d2f7a1946b → d4e6c8a109bf`.
- Fresh migration and upgrade from `c8d2f7a1946b` were exercised on temporary SQLite databases. Existing records survived the tested upgrade; the relationship confidence CHECK constraint remained present. The actual database was not upgraded.
- The Microsoft run, synthetic feedback, proposal, and RAG checks used `nexus-e2e-product-audit-8021-20261112.db` under the OS temporary directory. The existing listener on port 8000 and the actual development database were not used for writes.
- Existing 67 untracked team files/artifacts were preserved. No frontend file was changed.

## Automated verification

| Check | Result |
|---|---|
| Backend suite from repository root: `python -m pytest -q -p no:cacheprovider` | **203 passed, 0 failed, 0 skipped**, 17.92 s |
| Backend suite from `backend`: same command | **203 passed, 0 failed, 0 skipped**, 17.93 s |
| Migration regression tests: confidence constraint + KnowledgeItem migration | **9 passed**, 11.88 s |
| Frontend `npm run build` | **Passed**; Vite 8.3.6, 2,079 modules, 218 ms |
| Frontend lint/type scripts | No lint or type-check script is configured; `npm run` lists only `dev`, `build`, and `preview` |
| `git diff --check` | Passed |

Both complete test runs reported one existing Starlette/AnyIO deprecation warning (`anyio.abc.BlockingPortal` alias). The migration regressions are also included in the full suite. Test suites use temporary fixtures; no live-company network/Ollama dependency is required for them.

## Real-company collection and provenance

**Company:** Microsoft, a real public technology company not present in the actual local database when checked. The API created a separate audit company record in the temporary database.
**Configured LLM:** `qwen3:8b`.
**Embedding model:** `nomic-embed-text`, 768 dimensions.
**Research result:** 28.77 s; status `completed_with_errors`; 6 URLs discovered, 6 full documents collected and persisted, 0 fetch failures, 0 duplicate skips, 0 snippets. DDGS discovery was unavailable for the `product_updates`, `product_pages`, and `company_news` categories. The six successful records came from official `news.microsoft.com` pages, including same-domain discovery and DDGS leads. All were marked public. Collection time was 2026-11-12 UTC.

| Collected source | Type / usefulness | NEXUS publication date | Ingestion |
|---|---|---:|---|
| [Microsoft Source homepage](https://news.microsoft.com/) | Official company-news homepage; index, not an event record | unavailable | processed; 7 chunks |
| [Press releases archive](https://news.microsoft.com/source/tag/press-releases/) | Official archive index | unavailable | processed; 4 chunks |
| [Company News](https://news.microsoft.com/source/topics/company-news/) | Official news index | unavailable | processed; 4 chunks |
| [Corporate press materials](https://news.microsoft.com/microsoft-corporate-press-materials/) | Official press-materials landing page | unavailable | processed; 3 chunks |
| [Resources](https://news.microsoft.com/source/resources/) | Official resources page; little product-history evidence | unavailable | processed; 4 chunks |
| [Local know-how helps communities make the most of new technology and opportunities](https://news.microsoft.com/source/features/ai/local-know-how-helps-communities-make-the-most-of-new-technology-and-opportunities/) | Official Microsoft Source story; the only directly useful narrative in this small sample | null in NEXUS; official page says published Oct. 29, 2026 | extraction failed; 18 chunks persisted |

The official article reports that Microsoft supported an AI-literacy program with a public library system, which launched a pilot “a few months ago,” and that 18 people attended the first AI class in August. It does **not** give an exact pilot launch date. The attendance figure is participation, not evidence of program effectiveness. The page also discusses Climb Wyoming and Compudopt; their results must not be attributed to Microsoft. The official article and publication date were checked directly at the [Microsoft Source page](https://news.microsoft.com/source/features/ai/local-know-how-helps-communities-make-the-most-of-new-technology-and-opportunities/).

The other five pages are largely navigation or index pages. This is six collected documents, but only one useful narrative source—not a 5–10-document product-history corpus. NEXUS left publication dates null rather than inventing them. The publisher was `news.microsoft.com`; canonical/original URL, public permission, source category, and collection timestamp were stored. The source API does not return raw document text; RAG citations return the supporting passages.

## Ingestion and factual validation

The ingestion endpoint took **178.63 s** for six sources. It reported five processed and one failed, with **40 embedding chunks** generated. Five documents completed with empty event and knowledge-item arrays. The article failed at event extraction; the failure is distinct from an empty extraction result.

The confirmed failure was Ollama response truncation. Extraction tried `num_predict` budgets 2,048 then 4,096; the final response had `done_reason=length`, 18,152 characters, and malformed JSON (`Unterminated string` near character 18,147). The 15,225-character source therefore produced neither a ProductEvent nor a KnowledgeItem. The bounded retry worked as designed, but did not make this response usable. This article documents a community program, not a Microsoft product launch, so it must not be forced into a product-event record.

| Claim checked against the official article | Supported? | Date / classification | Notes |
|---|---|---|---|
| Microsoft supported a library AI-literacy program and the library system launched it as a pilot | Yes, directly stated | Exact pilot date unavailable; community program, not a Microsoft product launch | Extraction failed, so no event/knowledge record was persisted |
| 18 people attended the first AI class; turnout was nearly three times other classes in that town | Yes, directly stated | “In August”; year and exact class date not stated in that passage | Attendance only; not measured learning or business impact |
| Exact date the pilot began | No exact date supported | Unknown | Article says “a few months ago”; NEXUS and RAG left the date unknown |
| Microsoft product launch/update in this corpus | None established | Not applicable | No ProductEvent was extracted or persisted |

Metrics: **0 extracted events; 0 fully supported, 0 partially supported, 0 unsupported, 0 incorrectly dated, 0 event claims missing evidence, 0 duplicate events.** These are counts over zero persisted events, not a 100% accuracy result. Event precision/recall are **not measurable** from this run. One of six source ingestions failed; that is a processing failure, not a verified “no event” label. No KnowledgeItems were persisted.

## Retrieval, RAG, graph, feedback, and proposal checks

### Semantic retrieval and RAG

For “When did the Mecklenburg County Public Library AI training pilot launch, and what results did the article report?”, semantic retrieval returned relevant article chunks, but the original source-diversity selection could favor another page before the chunk containing attendance. The focused RAG change retains question-relevant passages from an already anchored source and prioritizes deferred passages that add a requested aspect, including when distinct pages fill the passage limit. A live request against the final code completed in **5.77 s**:

- `event`: supported with an exact source passage.
- `outcome`: supported as attendance (18 attendees, almost triple other classes), not efficacy.
- `date`: `not_found_in_verified_evidence`; the system did not infer a launch date.
- Answer status: `partially_answered`, with citations to the official source and supporting excerpts.

For a manually labelled passage set in this one-source query, Precision@3 was **2/3**: the first two passages were relevant to the Mecklenburg pilot; the third concerned a different organization in the same article. Recall@10 was **2/2** for the two manually labelled relevant passages. The answer cited both supported claims with passages matching the stored text (**2/2 citation coverage**). The stored article text contains replacement characters in some curly apostrophes (`Boyd�s`, `she�d`), although the official page uses typographic apostrophes. Thus exact source-text fidelity is not perfect for those characters; the fetching/decoding cause was not isolated. This small, single-article evaluation is not a general retrieval benchmark; text matching checks support by stored source text, not the truth of the publisher’s statement.

### Knowledge graph

The graph endpoint returned HTTP 200 and seven nodes (one company, six source documents), with zero edges. There were no event nodes, verified relationships, or causal links. Graph retrieval works; this real dataset did not validate relationship extraction or graph usefulness. The frontend graph was not visually inspected in a browser.

### Customer feedback

No real Microsoft customer reviews were collected. There is no automatic public-review discovery integration; the available inputs are API and CSV. A clearly labelled synthetic feedback record was submitted through the API in the temporary database, then reanalyzed and retrieved in feedback analysis/trends. Before the classifier fix, “The new bottle cap leaks after use. Please improve the cap design” returned neutral/design. After adding leak variants, reanalysis returned negative with design and reliability topics. This is one targeted synthetic example, not a classification-accuracy score. Feedback remains a heuristic customer signal, not proof of product events.

### Proposal analysis

One explicitly hypothetical proposal (“[HYPOTHETICAL] Extend local AI literacy workshops”; not a Microsoft plan) completed in approximately **21.8 s** during a warm local-model session, with fresh external research disabled. It used five same-company public evidence passages, zero external public passages, and no customer feedback. The recommendation was cautious: validate assumptions and target users, define measurable outcomes, and pilot before broad rollout. Model-attributed claims are not independently verified by the analysis call. The saved-analysis route initially mislabelled same-company public citations as `internal`; the route now uses `public_company`, verified by a regression test and by rereading the saved temporary analysis. The returned claims’ evidence classification remains `unknown`; they should not be presented as independently proven claims.

### Performance

| Operation | Measured result | Caveat |
|---|---:|---|
| Research | 28.77 s | One company/run; 6 sources |
| Ingestion | 178.63 s | One run; 6 documents, including one long extraction retry failure |
| Failed article ingestion interval | 120.52 s | Source start to failure timestamp, including bounded retry; not isolated model-only time |
| Semantic search | 2.14 s | One real query against the temporary corpus |
| RAG answer | 5.77 s | One final-code request through FastAPI TestClient with local Ollama |
| Proposal analysis | ~21.8 s | One warm-session request, external research disabled; not a cold/warm benchmark |
| Embedding generation | Not separately timed | 40 chunks persisted with `nomic-embed-text` |
| Frontend production build | 0.218 s | Vite build only; not browser loading performance |

`ollama list` showed `qwen3:8b`, `nomic-embed-text:latest`, and `llama3.2:3b`; the tested extraction/reasoning model was Qwen 3 8B. No repeated cold/warm timing series was run, so these are run measurements rather than reproducibility statistics.

## API and frontend integration

- `/health`, OpenAPI, company creation/retrieval, research stats, source listing, ingestion status, events, knowledge items, graph, feedback submission/analysis/trends, RAG, and saved proposal retrieval responded through the task-owned API instance. Health and configured CORS preflight both returned 200. The API instance used port 8021 and explicitly allowed the task-owned Vite origin `http://127.0.0.1:5177`.
- The frontend client uses the existing route methods and paths for research, source listing, events, graph, feedback analysis/trends/submission, chatbot, and proposal analysis. The production bundle passes.
- `docs/DATA_CONTRACT_v1.md` lists `GET /api/companies/{company_id}/feedback`, but this route is absent from OpenAPI and returned 404 when checked. The current frontend instead uses feedback analysis and trends, so it does not call that missing route. Do not expose raw feedback through a new unauthenticated endpoint without a privacy/authorization decision.
- The previously reported UI warning `ingestion failed to fetch; researchStatus failed to fetch` could not be reproduced or diagnosed in a browser. Direct ingestion-status and research-stats requests succeeded against the isolated API. The existing port-8000 app was not disturbed, so the warning’s exact URL, response body, and root cause remain **NOT TESTED**.
- Interactive browser automation was unavailable. No claim is made that screens, responsive layout, browser console, loading states, or the complete UI workflow were manually verified. The frontend has no configured lint/type-check script.

## Changes made

| File | Change |
|---|---|
| `backend/app/intelligence/rag.py` | Preserve deferred passages that cover missing requested answer aspects; recognize quantified attendance as a reported participation result, without implying effectiveness. |
| `backend/tests/test_rag_relevance.py` | Add synthetic regression coverage for attendance and same-source multi-part retrieval. |
| `backend/app/api/routes/proposals.py` | Classify persisted public same-company citations as `public_company`; retain `external` and `mixed` classification for saved claims. |
| `backend/tests/test_public_evidence_access.py` | Add synthetic temporary-SQLite API regression for saved public proposal provenance. |
| `backend/app/feedback/analyzer.py` | Normalize leak variants and classify them as negative reliability terms. |
| `backend/tests/test_workflow_integrations.py` | Add a labelled synthetic leak-complaint regression. |
| `docs/NEXUS_END_TO_END_AUDIT_REPORT.md` | Add this audit record. |

No shared contract, ORM schema, migration, frontend file, or actual database was changed. No files were staged, committed, pushed, reset, cleaned, or deleted.

## Remaining issues by priority

### Critical

None identified that prevents backend startup or production compilation. This does not imply production readiness.

### High

- Ollama/Qwen can truncate a long structured extraction response even after its bounded retry. The real article failed; improve long-document handling before demoing extraction on similarly long material.
- This real-company sample produced no ProductEvents or KnowledgeItems and no graph relationships. Do not demonstrate it as verified Microsoft product history.
- Browser-level verification and the known fetch warning remain unresolved; manually verify the actual target frontend/backend origin before the demo.

### Medium

- DDGS categories for product updates, product pages, and company news were unavailable during this run; collection returned mostly indexes and only one useful narrative article.
- The contract-documented company feedback-list endpoint is missing. The current UI does not depend on it; reconcile the contract and privacy boundary before implementing it.
- NEXUS did not extract publication dates in this source set. The official page’s October 29, 2026 publication date was independently checked; the pilot’s exact date remains unknown.
- The collected article text contains replacement characters for some typographic apostrophes; investigate response charset/decoding before treating excerpts as byte-for-byte source quotations.
- Real feedback and proposal-quality metrics are unavailable. Automatic external consumer-review collection is not implemented.
- Proposal recommendations and claims are model-attributed analysis; similarity and citations are not independent proof.

### Low

- The Starlette/AnyIO deprecation warning remains.
- No frontend lint or type-check script is configured.

## Manual demo steps and assessment

1. Start the backend and frontend with the intended local origin and verify `/health`, research stats, and ingestion status from the browser’s Network panel. Record the exact status/body if the prior fetch warning returns.
2. Use a prepared, permitted public source with an explicit product event for an extraction demonstration. Keep the Microsoft community article clearly labelled as community-program evidence, not a product event.
3. Present all generated customer-feedback examples as synthetic unless they come from a permitted, documented real dataset.
4. Explain that internal document import is local/trusted-development functionality; the application has no complete production authentication/authorization system.
5. Before any actual database migration, back up and verify the database, then migrate only after a separate temporary-copy upgrade check. Current actual revision is `c8d2f7a1946b`; head is `d4e6c8a109bf`.

**Final assessment: PARTIAL — reasonable for a supervised localhost demo using prepared evidence and explicit caveats; not validated as production-ready or as a fully reliable real-company product-history system.**

## Automated Onboarding Follow-up — 2026-11-12

### Implemented

- `POST /api/companies` now saves the company and schedules bounded onboarding when a website is supplied. It returns the existing 201 `CompanyOut` response; research status is available through the existing research-stats route. Companies without a website remain `not_started`.
- The in-process worker uses a session factory bound to the request's SQLAlchemy engine, marks status `queued`/`running`/`completed`/`partial`/`failed`, collects at most 6 pages at search depth 3, and processes at most 25 eligible sources. Repeated manual research is rejected with 409 while onboarding is queued or running. A per-process reservation prevents duplicate simultaneous jobs in the local server.
- The worker runs the existing relationship extractor after ingestion. It only considers two or more events linked to the same permitted source and relies on exact-quote plus semantic verification before persisting relationship provenance. Graph reads continue to build from persisted company, source, event and relationship records.
- The company dashboard polls research and ingestion status every 2.5 seconds while a run is queued or running. Expanded research details show event, knowledge-item and embedding counts from the existing research-stats response.
- For sources longer than 8,000 characters, structured extraction starts with an 8,192-token output budget and has one bounded 12,288-token retry. The extraction JSON schema and Pydantic validator cap knowledge items at four per source; the prompt asks for concise, distinct, high-value items. Malformed JSON is still rejected rather than partially accepted.

No shared data contract, ORM field, database schema, migration, or frontend API endpoint changed.

### Validation results

- A temporary SQLite database migrated from the beginning to Alembic head `d4e6c8a109bf`. The actual development database remains at `c8d2f7a1946b`; it was inspected read-only and not migrated or modified.
- The synthetic automatic-onboarding integration test created a company, collected and persisted a labelled synthetic source, ingested two labelled synthetic events, persisted embeddings, extracted one explicitly supported relationship with its exact source quote, and retrieved that relationship through the graph API.
- Full backend suite: **157 passed from repository root** and **157 passed from `backend`**. Migration regression subset: **9 passed**. Frontend production build: **passed** (Vite, 218 ms). Interactive browser verification remains not tested.
- On the previously collected 15,225-character Microsoft community-program article, the final end-to-end extraction call with the local Qwen model completed in **28.33 s** without a truncation/JSON error and the evidence validators retained **0 events and 0 knowledge items**. This is the appropriate result for this article's content; it does not establish product-event extraction recall. A prior unbounded-output attempt against the same source had failed with `done_reason=length` and a 36,179-character response.

### Real-company onboarding attempts

These tests used a separate temporary SQLite database at Alembic head, real public HTTP/DDGS discovery, and the application's actual onboarding worker. They were bounded to two pages and two ingestion candidates per company. No data was inserted into the development database.

| Company | Research result | Sources collected | Ingestion / events / knowledge / embeddings | Notes |
|---|---|---:|---|---|
| Fogg | `partial`; 1 URL discovered, 1 skipped, 0 fetch failures | 0 | 0 / 0 / 0 / 0 | A candidate did not pass the existing page-quality filter; DDGS returned a safe runtime failure. |
| Netflix | `partial`; 1 URL discovered, 1 skipped, 0 fetch failures | 0 | 0 / 0 / 0 / 0 | Official about-site sitemap alternatives returned HTTP 404; DDGS returned a safe runtime failure. |

These are real discovery attempts, not successful content evaluations. They did not validate extraction, persistence, retrieval, or proposal quality on either company. The system correctly reports partial research and zero evidence rather than inventing records.

### Fogg proposal evidence diagnostic

The requested analysis ID `ee471427-52ff-40c9-a08f-db807b6a78c8` was inspected read-only. Its persisted analysis had no `analysis_evidence` rows and reported 12 external passages excluded, no same-company passage over the 0.70 proposal threshold, and no completed feedback. I re-ran embedding retrieval and the existing Qwen relevance classifier against the stored corpus without writing to the database: all 12 retrieved external passages were excluded (10 `unrelated`, 2 `contextual`, 0 `direct_match`). The top candidates included unrelated textile, apparel and appliance pages; the two contextual passages were current TRESemmé hair-care catalog pages, not documented Fogg deodorant/fragrance history. The classifier's conservative exclusions are appropriate. The demonstrated issue is low-precision external candidate retrieval against a noisy stored corpus, not evidence that those passages should be admitted. I did not lower thresholds or promote competitor material to target-company history. The saved recommendation remains conservative because the available evidence is insufficient.

### Remaining blockers and limitations

- **High:** Both real-company runs found no full documents. Re-run live research when DDGS/network service is healthy, then independently validate any collected pages before presenting them as evidence. The current real-world two-company validation is **PARTIAL**, not passed end to end.
- **High:** FastAPI `BackgroundTasks` run in process and are not durable across a server crash/restart; the reservation lock is process-local. This is suitable only for a supervised single-process localhost demo, not production job execution.
- **High:** The prior browser warning `ingestion: Failed to fetch` / `researchStats: Failed to fetch` was not reproduced in a browser. Polling is now implemented, and the existing API paths are covered by backend integration tests, but the original warning's root cause is still **NOT TESTED**.
- **Medium:** The long-source knowledge-item cap of four bounds generation size and may omit lower-priority distinct items. Review the source and its citations for completeness before relying on it.
- **Medium:** The Fogg external-candidate set has low precision in the currently stored corpus. No evidence supports a Fogg-specific recommendation; do not present the external candidates as Fogg history.
- **Medium:** Real-company graph relationships were not validated because no sources/events were collected. The synthetic integration test verifies the guarded relationship-to-provenance path only.

### Files changed in this follow-up

- `backend/app/api/routes/companies.py`
- `backend/app/research/onboarding.py` (new)
- `backend/app/intelligence/extraction.py`
- `backend/tests/test_company_onboarding.py` (new)
- `backend/tests/test_extraction_pipeline.py`
- `backend/tests/test_workflow_integrations.py`
- `frontend/src/components/CompanyDashboard.jsx`
- `frontend/src/components/CompanyIntelligence.jsx`
- `docs/NEXUS_END_TO_END_AUDIT_REPORT.md`

Previously dirty proposal, feedback, RAG, and associated test changes were preserved. No commit or push was made.

**Follow-up assessment: PARTIAL — automatic onboarding is covered with isolated synthetic end-to-end tests and the long-source parser now succeeds on the known real article. Real Fogg and Netflix source collection did not produce documents, so a real-company end-to-end demo still requires successful live discovery and independent evidence review.**

## RAG Multi-Fact Completeness Regression — 2026-11-12

The prior internal synthetic RAG check exposed a confirmed completeness gap: a question asking which variants were compared, how many users participated, and what outcome was measured did not register participation as a requested aspect. The answer could therefore be marked complete without addressing every requested fact. Participation evidence phrased naturally as “40 fictional pilot users participated” also failed because the matcher required the count to immediately precede “users.”

The matcher now tracks explicit comparison and participation requests separately, recognizes comparison wording tied to two alternatives, and allows up to three descriptive words between a count and a participant category while still requiring a participation verb. The existing outcome and all-requested-aspects completion rule remains in force; an answer is complete only when verified claims cover every detected aspect. No evidence checks were weakened.

Regression coverage uses a labelled synthetic passage and verifies all three distinct facts receive verified citations and supported aspect states. Existing partial-answer integration coverage continues to verify that evidence for some requested aspects does not yield a complete answer when another is missing.

### Verification

- Backend suite from repository root: **158 passed** (`17.27 s`).
- Backend suite from `backend`: **158 passed** (`17.23 s`).
- Temporary-SQLite migration regression subset: **9 passed** (`11.94 s`).
- Frontend production build: **passed** (Vite, `221 ms`).
- Focused multipart RAG regression: **passed**.

Files changed for this follow-up: `backend/app/intelligence/rag.py`, `backend/tests/test_workflow_integrations.py`, and this report. No API contract, ORM schema, migration, frontend source, or actual database was changed. The full backend and frontend validations were run; interactive browser verification remains outstanding as noted above.

## Autonomous completion and proposal evidence verification — 2026-11-12

### Implementation and focused checks

The proposal evidence implementation now uses the configured Qwen/Ollama client for domain-independent passage classification. It distinguishes direct relevance, same-company history, competitor context, general industry context, related-but-insufficient passages, and irrelevant passages, and carries the selected proposal aspect and explanation through the response. The classifier receives source publisher/title/text but not source IDs or URLs; Python retains provenance. A separate query-generation call is bounded to 15 seconds and at most three normalized queries. Fresh competitor search uses the existing shared DDGS discovery path and existing URL/fetch restrictions; fresh search is opt-in, and provider failure is reported rather than represented as successful collection.

Claim citations selected by the proposal model are treated as candidates. The citation verifier receives the exact claim, original passage and source attribution; only accepted source IDs survive. Unknown model source IDs are filtered by Python. Verification failure is fail-closed: an unsupported factual claim loses its citation and is downgraded to a hypothesis. Regression tests cover a synthetic Gorilla Wear bottle passage against a hypothetical Milton ThermoSmart proposal.

The live synthetic-model check against the configured Qwen 3 8B returned `competitor_context` for the Gorilla Wear passage and preserved its exact synthetic source ID and URL in application-owned metadata. The same model verifier rejected a proposed claim that Milton had launched that feature; no citation was accepted. This is a focused model behavior check, not an accuracy benchmark or real-company evidence validation. Automated focused coverage: **38 passed**.

### Real-browser and isolated API exercise

The required Computer Use browser navigation was blocked by the desktop automation safety layer, which could not verify the active Windows browser URL. Computer Use was stopped as required. No interactive browser session or browser-console inspection is claimed. The existing Vite page and component module URLs were reachable over HTTP; the running app returned 200 for the page and the Dashboard, Research Sources, Knowledge Graph, Customer Intelligence, Proposal Analysis, and AI Assistant modules. Frontend lint/type scripts are not configured.

The running API used the temporary database `C:\Users\KARTHIK G A\AppData\Local\Temp\nexus_autonomous_qa_20261112_9f3d1b2c.sqlite`, migrated to `d4e6c8a109bf`. The actual development database was not used or changed. A company named **NEXUS Autonomous QA Demo 2026** was created there with an explicit synthetic-only description and no website. Company create/list/detail and company-isolated empty endpoints returned expected results: zero sources, events, KnowledgeItems, graph edges and customer feedback. Research correctly returned HTTP 400 because no website was configured; no live discovery or third-party fetch was attempted for this test company.

A hypothetical, explicitly labelled temperature-indicator proposal returned HTTP 200 with a conservative “insufficient documentary evidence” recommendation, zero evidence citations, zero feedback records and external-research status `unavailable` (fresh research was not requested). The RAG answer endpoint returned HTTP 200 and explicitly reported insufficient evidence. A text fixture that explicitly disclaimed any company/product/event facts was uploaded with `is_synthetic=true`; the API returned `evidence_origin=synthetic_demo`. Internal-source listing returned the item; ingestion completed with one embedding chunk, zero events, zero KnowledgeItems and no failed documents; RAG still returned insufficient evidence and did not invent an event. Synthetic feedback was submitted solely to exercise the feedback endpoint and was counted as one neutral “support” record; it is not customer evidence and is isolated to the temporary QA database.

Health returned 200. CORS preflight passed for the configured `http://localhost:5173` and `http://127.0.0.1:5173` origins. The alternate task Vite port `5179` is not in the configured CORS allowlist and correctly failed preflight; no allowlist was broadened. Use the configured port 5173 for browser/API integration.

### Final verification

- Full backend suite from repository root: **214 passed, 0 failed**, 19.69 s.
- Full backend suite from `backend`: **214 passed, 0 failed**, 19.65 s.
- Focused proposal relevance, citation verification, competitor discovery and transaction tests: **38 passed**, 0.77 s.
- Temporary SQLite migration regression tests: **9 passed**, 11.57 s. The isolated QA database reports revision `d4e6c8a109bf`; no migration was run against the development database.
- Frontend production build: **passed**, Vite 8.3.6, 2,079 modules, 228 ms.
- `git diff --check`: **passed** (Git emitted line-ending normalization warnings for three changed files; no whitespace errors).
- Ollama availability: `/api/tags` returned `qwen3:8b` and `nomic-embed-text:latest`.

### Remaining limitations and release decision

- **High / not verified:** interactive real-browser navigation, visible loading/error behavior, browser console/network inspection, and company-selection clicks remain untested because Computer Use was unavailable. Direct HTTP checks are not a substitute for this UI pass.
- **Medium:** live research was intentionally not run for the synthetic QA company because it has no configured website. Its research action was verified only for the honest missing-website error. Live DDGS/external collection was not part of this smoke run.
- **Medium:** the CORS configuration supports the intended 5173 origin; the task-owned Vite server also ran on 5179, which is intentionally disallowed. Use port 5173 or set an explicit local development allowlist before using a different port.
- The AI/model smoke sample is synthetic and singular. It does not establish general classifier or citation-verifier accuracy.

**Commit/push decision: not ready.** The user authorized commit and push only after all critical checks pass; the required interactive browser verification did not run. No staging, commit or push was performed. The branch remains `feature/ai-intelligence` at `ee1e9b5`, already two commits ahead of `origin/feature/ai-intelligence`. Pre-existing modified files, backups, archives and untracked team artifacts were preserved. The only documented task report update is this file; no database, ORM schema, migration or frontend source was modified during this final evidence-check pass.

### Local startup commands (PowerShell)

In separate PowerShell terminals, start the backend from `backend` so the repository's existing relative `.env` and SQLite paths retain their intended working directory:

```powershell
Set-Location backend
$env:NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES = "1" # trusted local demo only
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
Set-Location frontend
$env:VITE_API_BASE_URL = "http://127.0.0.1:8000"+npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173`. Do not use the internal-document toggle outside trusted local development; this API has no user authentication/authorization layer.

## Final real-browser verification — 2026-11-12

### Browser and environment

- Opened the actual Vite app at `http://localhost:5173` in Headless Chrome 157.0.8103.51 using the Chrome DevTools Protocol (Node WebSocket client). Interactions used browser mouse/keyboard events and the browser DOM; this was an interactive browser run, not only a build or HTTP smoke test.
- Confirmed the Vite frontend and FastAPI backend were already running on ports 5173 and 8000. No duplicate server was started.
- Created **NEXUS Autonomous QA Demo 2026** through the UI because it was not in the existing company list. It has no website. Its ID is `5cba527e-c4ff-4fd7-bce4-926701e9e29c`.
- Imported one explicitly synthetic, no-claims Markdown document through the local internal-source UI (synthetic label enabled). No research, document processing, migration, or operation on existing company data was run. The newly created QA company and this labelled synthetic source remain in the local development DB; neither was removed.

### Component results

| Frontend area | Result | Browser verification |
|---|---|---|
| Company Dashboard | PARTIAL | Opened the test company, inspected the summary and expanded/collapsed “View all extracted data.” Counts and “no verified events” state were accurate. Research/ingestion status and the knowledge-item request fail as detailed below. |
| Product Timeline | PASS | Opened timeline, confirmed zero-event state, typed a product search, and used the event category filter. It remained an honest empty state. |
| Research Sources | PARTIAL | Opened source view and source search/filter. It showed zero public sources and disabled research because the company has no website. Research statistics fail at the backend, so live research and source collection were not exercised. |
| Knowledge Graph | PARTIAL | Opened the graph, selected the company node, and confirmed zero evidence-backed edges. No relationship data existed to exercise edge details. |
| Customer Intelligence | PARTIAL | Opened the section, inspected the empty-feedback state and sentiment filter. No feedback was submitted or invented; a populated feedback workflow therefore remains unverified. |
| Proposal Analysis | PARTIAL | Submitted a clearly labelled hypothetical temperature-display bottle proposal. The API returned 200 and the UI rendered its recommendation and retrieved evidence. Relevance categories/reasons were visible; unsupported claim citations were absent. Retrieved passages included broad external/competitor context rather than verified NEXUS company history, so this is not evidence of a real-company recommendation workflow. |
| AI Assistant | PASS | Asked which verified events, launch dates, and outcomes were documented. The answer reported insufficient evidence, each aspect as not found, and no citations. |
| Company selection and navigation | PASS | Confirmed the test company appeared in the list, opened it, switched to an existing Thermos company, then returned to the QA company. The heading and displayed company-specific counts changed with selection; no cross-company event/feedback/source leakage was observed in these empty-state checks. |
| Internal document import | PARTIAL | With trusted-local access enabled, imported the labelled synthetic Markdown through the UI and confirmed the success message/source listing. Extraction/embedding processing was not run against the old development schema. |

### Failures, fix, and retest

The browser Network panel recorded HTTP 500 responses for these test-company requests:

- `GET /api/companies/5cba527e-c4ff-4fd7-bce4-926701e9e29c/research-stats`
- `GET /api/companies/5cba527e-c4ff-4fd7-bce4-926701e9e29c/knowledge-items`
- `GET /api/ingestion/companies/5cba527e-c4ff-4fd7-bce4-926701e9e29c/status`

Each is surfaced to `fetch` as `net::ERR_FAILED`; the 500 responses do not include the CORS header, so Chromium cannot expose their response bodies to the frontend. Direct read-only requests reproduced all three 500s. The existing local SQLite DB is at revision `c8d2f7a1946b` while the migration head is `d4e6c8a109bf`; read-only inspection had found the `research_runs` and `knowledge_items` tables missing. No migration was attempted. This is a database upgrade prerequisite, not a UI issue that can safely be masked in this verification pass.

One responsive bug was reproduced at a 390 px viewport: the expanded desktop sidebar consumed most of the viewport and clipped the company workspace. The sidebar now collapses to a 64 px icon rail at small widths, with accessible labels retained. After the fix, Chromium measured `innerWidth=390`, `visualViewport.width=390`, `scrollWidth=390`, and no horizontal overflow; the company title and timeline remained visible. A production build after the CSS/ARIA change passed.

The proposal page previously hid passage relevance metadata. It now displays the relevance category, proposal aspect and model explanation, and clarifies that retrieved context is not itself a verified claim. Chromium retest showed these labels and explanations on evidence cards while unsupported claims remained uncited.

Browser console/runtime checks found no JavaScript exceptions during the final home-page reload. The dashboard Network run confirmed the three HTTP 500s above. The home-page reload also returned `404` for `/favicon.ico`; this did not block rendering or navigation. No other failed network request was observed in the final isolated reload.

### Verification and changed files

- Frontend production build after the fixes: **passed** (`npm run build`, Vite 8.3.6, 2,079 modules, 203 ms).
- `git diff --check`: **passed**; Git emitted existing line-ending normalization warnings only.
- Backend suite and migration tests were **not rerun in this browser-only pass** because no backend, ORM, migration, or test source was changed. The prior report records 214 backend tests and 9 temporary-SQLite migration regression tests passing; those are prior results, not new runs here.
- Files modified for this browser pass: `frontend/src/components/CompanySidebar.jsx`, `frontend/src/components/CompanySidebar.css`, `frontend/src/components/ProposalAnalysis.jsx`, `frontend/src/components/CompanyDashboard.css`, and this report.
- No commit or push was made. Existing dirty and untracked team files were preserved.

### Release assessment

**Interactive frontend verification: PARTIAL.** Navigation, empty states, proposal submission, RAG insufficiency handling, local synthetic import, and mobile layout were exercised in a real browser. **The application is not ready for an unqualified demo against the current development DB** while the three endpoints above return 500. Before demonstrating research status, KnowledgeItems, or ingestion status, an authorized maintainer should back up and verify a copy of the DB, upgrade the actual DB using the established migration process, then repeat these browser checks. No DB upgrade is performed by this report.
