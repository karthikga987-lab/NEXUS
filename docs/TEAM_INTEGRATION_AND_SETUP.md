# NEXUS Team Integration and Local Setup

This guide describes the current shared integration branch and how each team member can run it. The integrated implementation is based on the AI-intelligence branch and selectively retains compatible capabilities from the other branches. It is not a wholesale merge of the historical branches.

## Branch and integration record

Remote references inspected for this integration:

| Branch | Inspected tip | Integration decision |
|---|---:|---|
| `main` | `19f1f6d` | Preserved as the review/PR target; not modified. |
| `feature/frontend` | `947138e` | Already an ancestor of the AI integration history; its latest UI work is present. |
| `feature/data-collection` | `35e281c` | Compatible research capabilities are represented in the integrated architecture. The branch itself is not merged because it carries a separate Alembic root, a separate internal-source model, and Gemini extraction code. |
| `feature/ai-intelligence` | `6ea6c33` | Base for `integration/team-integration`; contains the current AI, API, frontend, research and feedback integration. |
| `feature/customer-intelligence` | `924ef0d` | Its feedback capabilities are represented in the current app. The branch is not merged because it is based on the starter and replaces/removes the newer AI schema, routes and frontend. |
| `backup/ai-before-team-integration` | `6ea6c33` | Preserved unchanged. |

The local `integration/team-integration` branch was created from `6ea6c33`. Integration changes are reviewed and committed there, then that branch is pushed and proposed to `main` through a pull request. No team feature branch or `main` should be force-updated.

### Why the older feature branches are not merged wholesale

Member 2's migrations form a separate chain (`9efb883e2836 → 0ac08409d00a → 6a0d4b719c21`) under `backend/alembic/versions`, separate from the current `backend/migrations/versions` chain. Its guide describes a second `InternalSource` model and Gemini event extraction. The integrated app uses one canonical `SourceDocument` table for public sources and explicitly authorized local text sources, evidence-linked `KnowledgeItem` records, and the existing Ollama/Qwen extraction pipeline. Copying both model/migration lineages would create duplicate schema ownership and could break current foreign keys.

Member 4's branch is based on the starter and replaces its feedback API/model implementation. The integrated app already has company-scoped feedback persistence and analysis, public-source provenance checks, reanalysis, feedback trends, and a registered CSV upload route. Its richer current models and router are retained. The classifier is heuristic; this is not automatic public review collection.

Member 1's latest branch tip `947138e` is already in the integration history, so no component overwrite or frontend branch merge is needed here.

## Integrated capability map

| Member | Current integration |
|---|---|
| Member 1 — UI | React/Vite company selection and dashboard, research/source details, product timeline, knowledge graph, customer intelligence, proposal analysis, and AI Assistant call the current API client. Real API responses drive displayed records. |
| Member 2 — collection | Bounded DDGS search plus homepage, sitemap and same-domain discovery; normalized/deduplicated candidates; robots-aware and SSRF/redirect-protected fetches; HTML text processing; source persistence, snippets-vs-full-document distinction, failure diagnostics and persisted research-run status. Internal import accepts authorized local `.txt`/`.md` content only. |
| Member 3 — AI | Ollama/Qwen structured extraction and reasoning, exact-quote verification, ProductEvents and KnowledgeItems, evidence-linked relationships, 768-dimensional nomic embeddings, semantic retrieval, RAG, proposal analysis and saved evidence snapshots. |
| Member 4 — customer intelligence | Company-scoped feedback submission/listing, heuristic sentiment/topic analysis, trends, reanalysis, CSV upload API, and feedback context for supported proposal/RAG paths. Feedback remains distinct from documentary proof of product events. |

The endpoint map is visible in FastAPI at `/docs`. Main routes include company/source/event/research routes under `/api/companies`, graph routes under `/api/companies`, ingestion under `/api/ingestion`, feedback under `/api/feedback`, proposals under `/api/proposals`, and semantic/RAG routes under `/api/ai`.

The CSV endpoint is backend-only; the current frontend does not present a CSV upload control. Public review discovery is also not implemented. These are explicit integration limits, not implied functionality.

## Contract and database

`docs/DATA_CONTRACT_v1.md` is the shared authority. Its original v1 entities, fields, enum values and routes are retained. The file contains an appended additive extension for KnowledgeItems, ResearchRuns, optional source provenance responses, saved proposals, background research mode and analysis evidence snapshots. No data contract, ORM schema or migration was changed for this team-integration documentation pass.

There is one canonical Alembic directory: `backend/migrations/versions`. Its single head is `a83f4d129c71`, with the chain:

```text
913b86744127 → e02a9b9d1e2e → b7c4e91a2f63 → c8d2f7a1946b
             → d4e6c8a109bf → a83f4d129c71
```

The separate `backend/alembic/versions` lineage from Member 2's branch must not be copied into this repository. This integration did not connect to, upgrade, or otherwise modify an existing development database. Before upgrading an existing local database, make a verified backup and test the upgrade on a temporary copy.

## Setup on Windows PowerShell

Prerequisites: Python 3.11+, Node.js 20+, Git, and Ollama for AI model features. Clone the shared integration branch:

```powershell
git clone --branch integration/team-integration --single-branch https://github.com/karthikga987-lab/NEXUS.git
Set-Location NEXUS
```

### Backend and database

```powershell
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item ..\.env.example .env }
```

The example config uses SQLite at `backend/nexus.db` when commands run from `backend/`. On a fresh clone with no database file, create the schema through Alembic and start the API:

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --env-file .env
```

If `backend/nexus.db` already exists, inspect and back it up before any upgrade; do not use the fresh-clone commands as a substitute for migration review. To use PostgreSQL, set `DATABASE_URL` in the untracked `backend/.env` to a local/team-managed PostgreSQL URL. Do not put real credentials in `.env.example` or Git.

### Ollama

Keep Ollama running at the configured local endpoint, then install the configured models:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

`backend/.env` can override `NEXUS_OLLAMA_URL` and `NEXUS_OLLAMA_MODEL`. Search discovery uses DDGS and may return no candidates if upstream search providers are unavailable or rate-limit the request.

### Frontend

In a separate terminal from the repository root:

```powershell
Set-Location frontend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm ci
npm.cmd run dev
```

Use the Vite URL printed in the terminal (normally `http://localhost:5173`). `VITE_API_BASE_URL` defaults to `http://127.0.0.1:8000`. `npm.cmd` works around PowerShell's script policy blocking `npm.ps1`.

### Regression and build checks

From the repository root:

```powershell
python -m pytest backend/tests -q
```

From `frontend/`:

```powershell
node --test tests/*.test.js
npm.cmd run build
```

No frontend lint or type-check script is currently defined in `frontend/package.json`.

## Team contribution workflow

Keep `integration/team-integration` as the shared integration target. Each member creates a small task branch from that branch, pushes only that branch, and opens a pull request back to `integration/team-integration`. Resolve contract, model, or migration proposals with the team before implementation. The integration maintainer reviews and tests the combined branch, then opens a pull request from `integration/team-integration` to `main`. Keep the four original member branches and the backup branch intact.

Example task branch:

```powershell
git fetch origin
git switch --create feature/member-task origin/integration/team-integration
```

## Shared access and deployment boundary

GitHub shares the codebase only. It does not share a running NEXUS API, database, Ollama process/models, local documents, or environment variables. A shared hosted deployment would require a hosted frontend, secured API, managed PostgreSQL, private secret configuration, durable background-job processing, network-accessible model service, monitoring, backups, and authentication/authorization. None is provisioned by this repository task.

Internal-source access is disabled by default. Setting `NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES=1` only permits trusted loopback development access; it is not production authorization. Do not expose the unauthenticated API or internal-source feature to an untrusted network. Public research remains subject to robots policy, site access controls, rate limits, and source quality. Customer feedback classifications are heuristic and should not be described as ground truth.
