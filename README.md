# NEXUS — Product Knowledge and Decision Intelligence

NEXUS is a shared four-member project that collects eligible public sources, preserves source provenance, extracts evidence-linked product knowledge, and supports company-scoped feedback, search, RAG, knowledge-graph, and proposal-analysis workflows.

The integration branch is `integration/team-integration`. See [the team integration and setup guide](docs/TEAM_INTEGRATION_AND_SETUP.md) for the branch rationale, feature map, safe database setup, local startup commands, known limitations, and team workflow.

## Current application

- `frontend/` — React and Vite company workspaces, research/source views, product timeline, knowledge graph, customer intelligence, proposal analysis, and AI Assistant.
- `backend/` — FastAPI, SQLAlchemy, canonical Alembic history, public research, local authorized text-source import, Qwen/Ollama extraction and reasoning, evidence verification, nomic embeddings, RAG, feedback analysis, and proposal persistence.
- `docs/DATA_CONTRACT_v1.md` — shared v1 contract plus its explicitly additive extension. Existing shared fields and enum values remain unchanged.

## Quick start — Windows PowerShell

Prerequisites: Python 3.11 or later, Node.js 20 or later, Git, and Ollama for model-backed extraction, embeddings, RAG, and proposal analysis.

### Backend

From the repository root:

```powershell
Set-Location backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item ..\.env.example .env }
```

For a new local clone, inspect that `backend/nexus.db` does not already contain data, then initialize the SQLite database from the canonical migration history and start the API:

```powershell
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --env-file .env
```

API health is at `http://127.0.0.1:8000/health`; interactive API documentation is at `http://127.0.0.1:8000/docs`.

If a database file already exists, do not treat it as a fresh database. Back it up and test the intended migration on a temporary copy before upgrading it. NEXUS does not share a database merely because the source branch is shared.

### Ollama

Install and start Ollama, then download the configured models in a separate terminal:

```powershell
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

The defaults use `http://localhost:11434`. Research discovery uses bounded DDGS public search and does not require an API key. External sites may deny access or limit requests; NEXUS respects those restrictions.

### Frontend

In a second terminal from the repository root:

```powershell
Set-Location frontend
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm ci
npm.cmd run dev
```

Open the Vite URL, normally `http://localhost:5173`. The frontend API URL is configured by `frontend/.env` using `VITE_API_BASE_URL`.

## Checks

Run the backend regression suite from the repository root:

```powershell
python -m pytest backend/tests -q
```

Run frontend unit tests and the production build from `frontend/`:

```powershell
node --test tests/*.test.js
npm.cmd run build
```

`npm.cmd` avoids PowerShell's `npm.ps1` execution-policy restriction. The current frontend package has no dedicated lint or type-check script.

## Data and security notes

- One canonical Alembic history lives in `backend/migrations/versions`; do not copy the separate historical `backend/alembic/versions` chain from Member 2's branch.
- Internal-source import supports local `.txt` and `.md` files. It is disabled by default; `NEXUS_ENABLE_LOCAL_INTERNAL_SOURCES=1` is for trusted loopback development only. The project has no general API authentication/authorization and must not be exposed as a production service.
- Feedback can be submitted through the API and imported through the backend CSV endpoint. Sentiment and topic labels are heuristic; public customer-review discovery is not implemented.
- Search snippets are discovery leads, not collected full documents and are not ingested as documentary evidence.
- Proposals and AI analysis are separate from historical product events. Recommendations remain limited by the persisted evidence.
- A public Git branch shares code, not a running backend, Ollama service, database, credentials, or uploaded documents.
