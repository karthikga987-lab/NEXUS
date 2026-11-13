# NEXUS Final AI Validation and Release Report

Evaluation date: 2026-11-11
Working copy: `work/NEXUS`
Database: temporary SQLite databases only for migration and real-source evaluation. The actual development database was not opened or modified.

## Executive assessment

The final pass found a reproducible false event classification, a causal graph edge inferred from non-causal wording, product-specific RAG relevance errors, an exact-date attribution error, weak passage ranking, and no automatic public-review collection. Narrow fixes were made for event type/evidence alignment, causal relationship validation, RAG topic matching, long event sentences, and exact-day completeness. Regression and full test suites pass.

NEXUS is **conditionally suitable for a supervised, narrow hackathon demonstration**, where a person checks the source excerpt and treats the AI output as a research aid. It is **not ready to be presented as an autonomous or dependable product decision engine**. Real evaluation used only two official pages and five questions; public customer feedback was unavailable, proposal outputs were generic pilots, and the corporate Lamellar Shine query failed to retrieve a useful passage.

## Real source collection

Both sources were public official Unilever pages fetched through NEXUS's existing safe fetcher, then passed through the existing page extraction, source persistence and embedding path. The recorded sources and collection outputs are in [`real_world_eval_results.json`](../backend/ai_evaluation/real_world_eval_results.json).

| Scope | Source and URL | Publication date recorded | Product/event date | Access and metadata |
|---|---|---|---|---|
| TRESemmé brand | [TRESemmé Professional: science-led, salon-quality haircare](https://www.unilever.com/news/news-search/2026/tresemmes-transformation-introducing-the-brands-new-science-led-salon-quality-haircare/) | 9 July 2026, parsed from page metadata | Launch in UK and Ireland in May 2026; no exact day documented | Public; publisher recorded as Unilever; `official_company_news`; URL, excerpt, publication date, source type, permission status and collection timestamp retained. SQLite serialized the collection timestamp without a timezone offset. |
| Unilever corporate | [Improved performance led by volume growth and gross margin expansion](https://www.unilever.com/news/press-and-media/press-releases/2025/improved-performance-led-by-volume-growth-and-gross-margin-expansion/) | 13 February 2025, parsed from page metadata | The release says TRESemmé grew mid-single digit following the Lamellar Shine collection launch; it does not establish an exact launch day or prove that the collection caused the growth. | Public; publisher recorded as Unilever; `official_press_release`; stored under a separate Unilever PLC company record to preserve corporate versus brand scope. |

The first article also describes six benefit areas for the TRESemmé Professional range: strengthening damaged hair, hydration, frizz control, shine, colour protection, and curl definition. These are documented product benefits, not six separately dated launches. The second page reports group-level annual results and a TRESemmé subsection; its Unilever-wide figures were not attributed to TRESemmé.

An official [TRESemmé product page](https://www.tresemme.com/uk/p/tresemm%C3%A9-freeze-hold-hairspray-400ml.html/08710447299104) was identified, but the NEXUS safe fetcher timed out when accessing its review content. No review text was collected, no access restriction was bypassed, and no real feedback labels or metrics are claimed.

The source excerpts, publisher, URLs, available publication dates, source type, public permission status, and collection timestamps are preserved in the evaluation output. Actual event dates are recorded only when source evidence supports them. Collection timestamps were returned from SQLite without an offset; consumers should not assume a timezone from that serialized value alone.

## Product history extraction

The manually scoped reference set for the TRESemmé article contained one high-confidence product-history event: TRESemmé Professional launched in the UK and Ireland in May 2026. The final local Qwen 3 8B ingestion persisted exactly that event with its supporting source excerpt. `event_date` remains null because the source states only the month. No event-level launch reason or business outcome was inferred.

The earlier live pass also produced an “Appoints Influencer Partnerships” incident from a launch sentence about social-first influencer marketing. The cited text did not support an appointment or incident. A deterministic event-type/evidence check now rejects that candidate; a regression test preserves the failure case. The final pass persisted one launch event and no false appointment event. This is a one-document, one-target check, not a representative precision/recall estimate. The source does not provide a labeled inventory of every potentially extractable event, so broader extraction metrics are not defensible.

The article explicitly says the Thermo Sculpt Memory range was developed in response to the rise of heat styling. RAG retrieved and cited that reason. This pass did not identify a publicly documented experiment or controlled product outcome in the two collected pages; those fields remain unknown.

Across repeated real runs, the long article caused one Qwen extraction response to hit the output limit and retry with a larger budget. The retry completed. This is a reproducible reliability limitation worth monitoring on long pages.

## Public customer feedback

Automatic external customer-review discovery is **not implemented**. NEXUS API submission and CSV import are user-supplied feedback paths; they are not internet discovery. The official product review page could not be retrieved by the safe fetcher, so this evaluation has:

- 0 collected real review texts;
- 0 manually labeled real feedback examples;
- no real-world sentiment, product association, complaint, feature request, negation, duplicate, contradiction, or proposal-relevance scores.

The live deterministic classifier evaluation remains synthetic: the existing 12 labeled synthetic examples scored 12/12 for sentiment, feedback type, and expected topic presence. That result is not a real-customer accuracy estimate. Product resolution, sarcasm, context, multilingual feedback, and contradictory reviews remain unmeasured or limited. No public feedback was treated as documentary proof of a product event.

## Semantic retrieval and RAG

The real run used `nomic-embed-text` (768 dimensions) and Qwen 3 8B. Five multi-part/paraphrased questions were sent through the actual retrieval, candidate extraction, citation verification, and response path. The evaluator now records the top five chunk excerpts and similarity values, not only source IDs.

| Real question | Observed result |
|---|---|
| TRESemmé Professional launch timing and geography | Answered with the supported May 2026 timing and UK/Ireland geography. The recorded date and event aspects were supported. |
| Why Thermo Sculpt Memory was developed | The stated heat-styling reason was retrieved. The response also included one unsupported claim and tangential claims; treat the answer as requiring review. |
| Exact calendar day of TRESemmé Professional launch | Correctly marked partial: event supported, exact date not found. The article publication date is no longer accepted as the event day. |
| What Unilever reported about TRESemmé and Lamellar Shine | Insufficient evidence. Although the correct corporate document was retrieved, the top five passages were mostly safe-harbor, unrelated business text, or the site survey footer; the Lamellar Shine performance passage did not rank in the top five. |
| Exact Lamellar Shine launch date | Insufficient evidence, appropriately. No exact launch date was found in the collected corporate release or retrieved passages. |

All emitted citation quotations in the final real run were verbatim after whitespace normalization. This checks textual quotation integrity, not whether the quote is relevant to every interpretation of the question or independently true. The reason answer had one unsupported claim despite its relevant cited reason. Two of five questions returned insufficient evidence; one of those is an expected limitation (no exact Lamellar date), but the corporate performance query is a retrieval failure.

Document-level source recall was 1.0 in the five-query fixture because each company had only one stored source. That number hides passage-ranking failures and must not be represented as useful retrieval performance. Passage-level precision/recall was not calculated against a sufficiently broad manually labeled real corpus. The existing labeled synthetic retrieval run measured macro Precision@3 **0.2667** and Recall@3 **0.8000**; irrelevant retrieval therefore remains reproducible. The evaluator does not claim that source-level precision of 1.0 resolves it.

The exact-date guard now requires a full calendar date near explicit launch/availability wording and rejects publication-date language. Product-specific event/date candidate promotion now requires the sentence to overlap the queried product terms instead of relying only on the document title. Long completed event sentences up to a 1,200-character limit are retained for citation checking rather than dropped by the prior 700-character cap. Regression tests cover these cases. The Lamellar passage-ranking problem remains unfixed because the query's top five chunks did not contain the needed passage; broad retrieval redesign was out of scope for this freeze.

## Knowledge graph

The final TRESemmé graph contained three nodes (company, one launch event, one source) and two support edges (`HAS_EVENT` and `SUPPORTED_BY`). No event-to-event relationship was created because only one event survived extraction. The earlier run had proposed a `MOTIVATED_BY` edge from a launch sentence that only mentioned influencer marketing; temporal order or topical proximity did not establish cause.

Relationship validation now requires explicit causal language for `MOTIVATED_BY`, `RESULTED_IN`, `CHANGED_BECAUSE_OF`, and any relationship labeled `documented_cause`. “After” and other temporal-only wording is rejected. A regression test verifies that “introduced … after the plan update” cannot support a causal edge. This validates the gate, not general graph precision/recall; no labeled real graph corpus was available.

## Proposal intelligence

Two explicitly hypothetical TRESemmé proposals were analyzed: a possible US expansion and a packaging-material change. Both received the conservative generic `PILOT` recommendation. The pipeline did not find customer feedback, and the recommendations did not demonstrate a proposal-specific comparison against rich real product history. They are safe fallback outputs, not evidence that the proposals were company decisions or that the suggested pilots are optimal. No real customer signal or real decision was invented.

## Code changes and tests

Narrow changes made in this pass:

- Event extraction rejects an event type when its exact evidence quote lacks an action consistent with that type.
- Relationship validation rejects causal types without explicit causal wording.
- RAG drops question filler from topic matching, prevents product/date claims from borrowing unrelated sentences based on a page title, preserves heading context for reason/experiment/outcome sentences, and distinguishes an exact event date from article publication date.
- RAG keeps long completed event sentences within the embedding passage size range.
- The real evaluator scopes event evidence by company event IDs, normalizes whitespace for quotation integrity, computes distinct-source precision separately from recall, and stores top-five passage excerpts for auditability.

| Check | Result |
|---|---:|
| Backend suite from repository root: `python -m pytest backend` | **142 passed** (5.88 s) |
| Backend suite from backend directory: `python -m pytest` | **142 passed** (5.99 s) |
| Migration regression tests, temporary SQLite only | **4 passed** (4.62 s): fresh upgrade, previous-head upgrade with row preservation, safe stop on invalid legacy confidence, and safe downgrade preservation |
| Focused extraction, relationship and RAG regressions | **51 passed** (0.48 s) |
| Live synthetic event/feedback evaluation | Event precision 1.0000; recall 0.8571; matched-event type/date accuracy 1.0000; reason presence 0.8333; outcome presence 1.0000. Feedback sentiment/type/topic each 1.0000 on 12 synthetic examples. |
| Live synthetic retrieval/RAG | Macro Precision@3 0.2667; Recall@3 0.8000. All five expected aspect/status labels matched after the final changes; 0 unsupported claims in those five synthetic RAG cases. |
| Live synthetic proposal evaluation | 3/3 scenarios completed; source-ID/citation constraints passed; synthetic feedback signal appeared where expected. |
| Real source evaluation | Completed with the limitations above; two official sources, one persisted TRESemmé event, five RAG questions, two hypothetical proposals; temporary SQLite only. |
| Frontend production build: `npm run build` | **Passed**; Vite 8.3.6 transformed 2,060 modules and built in 614 ms. Frontend source files were not edited. |
| Ollama/model checks | Ollama 0.40.16 available; `qwen3:8b` and `nomic-embed-text:latest` installed and used; real embedding vectors were 768 dimensions. |

Migration history remained connected with one head, `c8d2f7a1946b`: `913b86744127 -> e02a9b9d1e2e -> b7c4e91a2f63 -> c8d2f7a1946b`. No migration file was changed in this pass. The shared contract and ORM/schema files were not changed; their hashes at completion match the protected working copy values. No frontend source, API contract, ORM field, or shared data contract was edited. The frontend build generated the normal `frontend/dist` outputs.

The current workspace has no `.git` directory. Therefore a Git branch, baseline diff, and Git status cannot be reported; no repository history was assumed. The verified shared-file hashes are `DATA_CONTRACT_v1.md` `fa3ca1e43c17b18ae215e76996a91f7695780e4ec239e5ba2f333233c47267fe`, `backend/app/models/entities.py` `48bcf39b5c4b20dbbb5c3db07aa0b360d1b584a0a70cfc6ca9e4575fb6e637a7`, and `backend/app/schemas/contracts.py` `7bc4f6c9731656f5e5cb3f65755cabb123d3a31e1f0235d242b82fd7b0d14fed`.

### Files changed or generated in this pass

- `backend/app/intelligence/extraction.py`
- `backend/app/intelligence/test_extraction.py`
- `backend/app/intelligence/relationship_extraction.py`
- `backend/tests/test_relationship_extraction.py`
- `backend/app/intelligence/rag.py`
- `backend/tests/test_rag_relevance.py`
- `backend/ai_evaluation/run_tresemme_real_eval.py`
- `backend/ai_evaluation/real_world_eval_results.json`
- `backend/ai_evaluation/latest_results.json`
- `backend/ai_evaluation/retrieval_rag_results.json`
- `backend/ai_evaluation/proposal_results.json`
- `docs/AI_INTELLIGENCE_QUALITY_AUDIT.md`
- `docs/NEXUS_FINAL_AI_VALIDATION_AND_RELEASE_REPORT.md`
- Build outputs generated by the required frontend build: `frontend/dist/index.html`, `frontend/dist/assets/index-BCnW1PcY.css`, and `frontend/dist/assets/index-BDyrjASq.js`.

## Freeze assessment and remaining work

| Priority | Finding |
|---|---|
| **Critical** | None found that prevents a supervised, source-checked demonstration. This is not an assurance of production safety. |
| **High** | Real passage ranking is weak: the Unilever/TRESemmé performance question fails; synthetic Precision@3 remains 0.2667. |
| **High** | Automatic review discovery is absent, and no real feedback dataset was available. Proposal analysis therefore has no real customer signal and produced generic pilot recommendations. |
| **High** | Qwen RAG may include tangential or unsupported claims; the real reason answer had one unsupported claim. Human review is required. |
| **Medium** | Long-source event extraction reaches the model output limit and depends on retry. |
| **Medium** | Relationship behavior was checked against one real event only; graph relationship quality lacks a labeled real benchmark. |
| **Low** | The SQLite-serialized collection timestamps lack an explicit UTC offset in the evaluation JSON. |

Before a demo, keep the two sources clearly labeled and linked; demonstrate only questions with source passages that visibly support the answer; say “exact day not documented” for the launch date; do not show public-feedback findings as real; label both proposals hypothetical; and manually check any recommendation, number, graph relationship, and source citation. A larger real corpus, manually labeled product-event/customer-review data, and improved chunk ranking are required before making stronger quality claims.

This report records the final planned AI validation pass. Implementation is frozen pending approval; no further refactoring or feature work is included.
