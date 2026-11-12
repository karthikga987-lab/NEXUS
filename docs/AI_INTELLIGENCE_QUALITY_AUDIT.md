# NEXUS AI Intelligence Quality Audit

Audit date: 2026-11-11
Working copy: `work/NEXUS`
Synthetic evaluations use invented Aster Works products, evidence, dates, feedback, and proposals. They are not claims about real companies. This earlier audit contained no real-company evaluation; the subsequent final real-source validation is documented in [`NEXUS_FINAL_AI_VALIDATION_AND_RELEASE_REPORT.md`](NEXUS_FINAL_AI_VALIDATION_AND_RELEASE_REPORT.md).

## Assessment

NEXUS has a working local-model and evidence-grounded pipeline, with useful source provenance and conservative handling of missing fields. The synthetic checks are encouraging for simple event extraction and feedback labels, but they also exposed missed events, noisy semantic retrieval, incomplete multi-part RAG answers, and generic proposal fallbacks. This is suitable for a supervised hackathon demo with clearly synthetic or source-attributed examples; it is not evidence of reliable real-world decision quality.

## Components and model execution

| Capability | Implementation | Method and audit notes |
|---|---|---|
| Event extraction | `backend/app/intelligence/extraction.py` | Ollama JSON extraction followed by deterministic validation of event fields, dates, completed actions, evidence excerpts, and source IDs. |
| Citation verification | `backend/app/intelligence/claim_verification.py` | Ollama-assisted claim-to-passage verification; accepted citations retain source identity and quote. Text support does not establish publisher truth. |
| Embeddings | `backend/app/intelligence/embeddings.py` | Ollama embedding endpoint; fixed model name `nomic-embed-text`; runtime vectors measured at 768 dimensions. Cosine ranking over persisted chunks. |
| RAG | `backend/app/intelligence/rag.py` | Retrieves permitted chunks, extracts source sentences, verifies quotes, classifies requested answer aspects, and labels partial/insufficient answers. Aspect recognition is heuristic. |
| Relationship extraction | `backend/app/intelligence/relationship_extraction.py` | Model-assisted extraction with relationship validation and provenance handling. |
| Knowledge graph | `backend/app/knowledge_graph/builder.py`, `backend/app/knowledge_graph/serialization.py` | Graph is built from persisted company, source, event, event-source, and relationship records. It does not infer a relationship from chronology. |
| Historical proposal relevance | `backend/app/intelligence/proposal_relevance.py` | Rule-based lexical fallback and Qwen classification for external passages; accepted evidence is still not proof of proposal success. |
| Proposal analysis | `backend/app/intelligence/proposal_analysis.py` | Qwen proposal reasoning, with source references and customer feedback kept distinct. A deterministic conservative fallback is used when model output is empty or generic. |
| Feedback ingestion/classification | `backend/app/api/routes/feedback.py`, `backend/app/feedback/csv_upload.py`, `backend/app/feedback/analyzer.py` | API and CSV ingestion; sentiment, type, and topics are deterministic keyword/rule classifications, not LLM analysis. |

The configured language model is `qwen3:8b` (`NEXUS_OLLAMA_MODEL`, default). The configured embedding model is `nomic-embed-text`. Ollama was available during the audit (`0.40.16`); `qwen3:8b`, `nomic-embed-text:latest`, and `llama3.2:3b` were installed. NEXUS used Qwen 3 8B for the actual extraction, RAG verification, and proposal runs; the installed Llama model was not used by NEXUS.

## Evaluation data and reproducibility

Labeled event and feedback fixtures are in `backend/ai_evaluation/synthetic_events.json`. The fixture contains five varied synthetic documents with seven expected events, including launch, removal, pricing, reformulation, a strategic decision, an experiment with conflicting dates, multiple products, irrelevant details, and a no-completed-event case. It also contains twelve labeled feedback examples including mixed sentiment, requests, complaints, questions, generic topics, and negation.

Live local evaluations:

```powershell
cd backend
python -m ai_evaluation.run_synthetic_eval
python -m ai_evaluation.run_retrieval_rag_eval
python -m ai_evaluation.run_proposal_eval
```

All database-backed evaluation data is written into temporary SQLite files. The committed evaluation outputs are snapshots of the actual run results, not model-independent guarantees.

## Event extraction

Results from the live `qwen3:8b` evaluation (`backend/ai_evaluation/latest_results.json`):

| Measure | Result |
|---|---:|
| Expected events | 7 |
| Validated predictions | 6 |
| Matched events | 6 |
| Event precision | 1.0000 |
| Event recall | 0.8571 |
| Event type exact accuracy on matched events | 1.0000 |
| Exact date accuracy on matched events | 1.0000 |
| Stated-reason presence accuracy | 0.8333 |
| Outcome presence accuracy | 1.0000 |

The model missed the separate Aster Calendar feature event in a long multi-product document. One feature-removal event omitted its stated reason. All matched source references and excerpts in this fixture were retained as the expected synthetic source ID and a verbatim excerpt. The small fixture does not establish broad precision/recall; product names are used for event matching and title/description/evidence-classification quality is not fully scored.

The validator previously rejected some exact evidence because the model concatenated non-contiguous snippets into one quote. It now only recovers an exact quote from the supplied product-name field when that text independently supports a completed event. Completed action verbs and explicit approved decisions are recognized more consistently. A test protects this behavior. The evaluator still correctly leaves absent reasons/outcomes unknown rather than filling them in.

## Customer feedback

Feedback currently enters by:

- `POST /api/feedback`: API-supplied records are associated with a company and analyzed at submission.
- `POST /api/feedback/upload-csv`: CSV-supplied records are analyzed and stored; duplicate handling is performed for repeated text/URL keys in the upload flow.
- External public-source research: **not implemented as automatic customer-feedback discovery**. Research collects company/source material; it does not crawl public review or social sites for feedback.

There is no separate automatic external feedback collection pipeline. Product text can be stored with feedback, but the evaluated sentiment/topic classifier does not perform robust product entity resolution. API duplicate behavior is not equivalent to CSV upload deduplication.

On the twelve labeled synthetic examples, the production rule classifier scored 12/12 for sentiment, 12/12 for feedback type, and 12/12 for the expected topic being present. This is a small hand-labeled fixture, not a population accuracy estimate. Topic overlap is allowed: the classifier can emit multiple topics and chooses one primary topic. Generic text falls back to a general topic. Negation handling and mixed sentiment have regression coverage, but sarcasm, context, multilingual feedback, and product association remain limitations. Feedback is a customer signal, not documentary proof of events or business outcomes.

## Embeddings and semantic retrieval

Actual `nomic-embed-text` vectors had 768 dimensions. The five labeled retrieval queries yielded macro Precision@3 of **0.2667** and macro Recall@3 of **0.8000** (`backend/ai_evaluation/retrieval_rag_results.json`). The expected source ranked first for all four answerable fixture queries, and returned results retained source ID, URL, and chunk text. However, the top-three lists included unrelated sources, reducing precision. The unrelated office-wall question still retrieved three synthetic sources; retrieval itself does not enforce a relevance cutoff. RAG withheld an answer for that question.

These values are corpus- and query-specific. The fixture tests launches, pricing, reformulation, experiment results, and an unrelated query. It does not separately evaluate customer complaint retrieval or a broad range of paraphrases/ambiguous queries.

## RAG

The live Qwen-backed synthetic run covered five questions: date/reason/event, a multi-part product question, experiment/result, price-change reason/outcome, and an unrelated question. All expected answer-aspect states matched the fixture; all expected-complete responses had `answered_with_verified_evidence`, and the unrelated question had `insufficient_evidence`. Accepted citation quotes were verbatim, with zero unsupported claims in these five outputs. Typical observed answer latency was about 2.1 seconds in this local run.

The evaluation found that citation verification alone did not ensure topical relevance: an earlier answer could attach an experiment result from a different product to a pricing question. Product-specific candidate extraction now requires overlap with the query or product context before promoting a generic event/outcome sentence. Regression coverage verifies that the price question does not borrow an unrelated experiment outcome. Broad questions without a product anchor intentionally admit retrieved candidates; cross-document identity and causal links still need careful user review.

RAG aspect checks are heuristic, and a verified quote may still be irrelevant to the intended entity or relation. The synthetic test does not cover contradictory sources exhaustively, independent truth checking, or production user questions. “Supported” means a retrieved verified sentence covers the requested aspect, including a source explicitly saying a reason/outcome was not reported; it does not mean the event had a positive outcome.

## Knowledge graph

The existing suite includes `backend/tests/test_knowledge_graph.py` and tests for event/source nodes, explicit persisted relationships, serialization, relationship direction, evidence classification, confidence, and provenance availability. Graph construction does not infer causal edges from date order. This audit did not run a separate model-quality score for relationship extraction against a labeled graph corpus, and it does not claim graph edge precision/recall. Stored relationships lacking source links are exposed with missing-provenance status and should not be treated as independently supported.

## Proposal analysis

Three labeled synthetic proposals were run against Qwen with synthetic feedback and one synthetic historical source. The mechanical checks verified a valid decision label on all three final outputs, and claim source IDs stayed within supplied evidence. Two proposals had relevant Orbit Desk context; the cleaning-concentrate proposal had no relevant history after the new internal relevance filter and correctly produced an insufficient-evidence pilot fallback without citing the pricing source.

The live run showed a meaningful limitation: Qwen produced a useful proposal-specific offline-mode recommendation, but returned a generic/non-company-anchored answer for the price increase, so the deterministic conservative `PILOT` fallback was used. The fallback is cautious, but it does not demonstrate that the model can reliably compare the proposal, evidence, and feedback. The analyzer now excludes clearly unrelated internal passages using a conservative lexical check and labels fallback recommendations explicitly. Contextual passages are retained, so the filter is not a semantic proof of relevance. Proposal recommendation quality remains a human-reviewed judgment; the evaluation checks provenance and shape, not correctness of business decisions.

## Feedback-to-proposal integration

Existing workflow integration tests cover feedback persistence, feedback analysis, and proposal retrieval of feedback. In the live synthetic proposals, supplied feedback appeared as a separate signal and was not used as a documentary citation. The analyzer includes limitations about feedback scope and heuristic sentiment/topic labels. Empty feedback is handled. Broader signal aggregation and contradictory feedback quality were not measured beyond the small fixture.

## Tests and separation of evidence

- **Unit/regression suite:** 134 backend tests passed from the repository root and 134 passed from `backend/` after the fixes. These tests establish code behavior for the tested cases; they do not prove model quality.
- **Synthetic rule/model evaluations:** event extraction and proposal/RAG evaluations used the actual local Qwen 3 8B model. Feedback classification used the production deterministic classifier. Embeddings and retrieval used actual local `nomic-embed-text`.
- **Local runtime evaluation:** Ollama was available and calls completed. Results and per-case latency are recorded in `backend/ai_evaluation/latest_results.json`, `backend/ai_evaluation/retrieval_rag_results.json`, and `backend/ai_evaluation/proposal_results.json`.
- **Real-company validation:** none. No real company data, real customer feedback, or independently labeled production sample was used.

## Remaining issues and demo readiness

| Priority | Issue |
|---|---|
| High | Semantic retrieval returns weak extra candidates and also retrieves for unrelated queries. Keep the current explicit insufficient-evidence behavior in demos and inspect citations. |
| High | Event extraction missed one multi-product event and omitted one explicit reason in this small run. Long multi-event documents need stronger evaluation before relying on completeness. |
| High | Proposal Qwen output fell back to generic text on one of three proposals. Treat recommendations as decision support requiring human review. |
| Medium | Product-level feedback association, API duplicate handling, and feedback classification beyond curated English examples are limited. |
| Medium | No independent labeled evaluation exists for knowledge graph relation extraction, contradictory evidence, proposal quality, or real-company behavior. |
| Low | Expand evaluation fixtures with paraphrases, more industries, additional languages, and independently reviewed labels before claiming generalized accuracy. |

**Readiness:** reasonable for a supervised hackathon demonstration using source-attributed evidence, synthetic examples, and human-reviewed proposals. Not ready to present outputs as autonomous or validated real-world company intelligence. No shared data contract, ORM schema, or frontend files were changed for this audit.
