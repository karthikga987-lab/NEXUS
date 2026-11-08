# NEXUS – Shared Starter Repository

A common starting point for all four team members. This is a **working scaffold**, not the finished intelligence engine. It gives the team one repository, a shared database model, common API contracts, frontend shell, and clear module ownership.

## Architecture

- `frontend/` – Member 1: React + Vite UI
- `backend/` – shared FastAPI application and database contracts
  - `research/` – Member 2
  - `intelligence/` and `knowledge_graph/` – Member 3
  - `feedback/` – Member 4
- `docs/` – shared API and data contracts
- `sample_data/` – clearly labelled demo fixtures only

## 1. Prerequisites

- Python 3.11+
- Node.js 20+
- Git
- PostgreSQL (optional initially; SQLite works for local scaffolding)

## 2. Run backend (Windows PowerShell)

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs`.

The starter uses SQLite by default, so the team can begin without setting up PostgreSQL. For shared integration, create a PostgreSQL database and set `DATABASE_URL` in `backend/.env`, for example:

```env
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/nexus
```

Then install `psycopg[binary]` (already included in requirements).

## 3. Run frontend

Open a second terminal:

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Open the Vite URL shown in the terminal. The frontend expects the API at `http://127.0.0.1:8000`.

## 4. Git collaboration

One person creates the GitHub repository and pushes this starter as `main`.

Each member then runs:

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd NEXUS
git checkout -b feature/frontend
```

Use the matching branch:
- Member 1: `feature/frontend`
- Member 2: `feature/data-collection`
- Member 3: `feature/ai-intelligence`
- Member 4: `feature/customer-intelligence`

Before starting a task, pull the latest `main`. Commit and push only your branch. Open a pull request to merge into `main`. Do not independently rename shared fields or change common models without discussing it first.

## 5. Shared rules

1. `company_id`, `source_id`, `event_id`, `proposal_id` and `feedback_id` are UUID strings.
2. Dates are ISO 8601 timestamps. Store UTC timestamps; display local time in the UI.
3. Every extracted factual claim/event must retain source references.
4. Do not treat sequence or correlation as proof of causation.
5. Use `evidence_classification`: `documented_cause`, `supported_relationship`, `correlation`, or `unknown`.
6. Do not invent missing dates, reasons, metrics, decisions, or outcomes.
7. Public data is not private internal company data. Internal integrations require company authorization.
8. Keep demo fixtures explicitly labelled as demo data.

## 6. First integration milestones

- Member 2 + Member 3: agree on source-document and product-event extraction fields before changing models.
- Member 1: build UI using the API and mock fixtures; don't wait for AI integration.
- Member 4: use the shared `Feedback` model and feedback endpoints.
- All: run the backend and frontend locally before merging.

## 7. API overview

- `GET /health`
- `POST /api/companies`
- `GET /api/companies`
- `GET /api/companies/{company_id}`
- `POST /api/companies/{company_id}/research` – placeholder job response; Member 2 implements the research pipeline
- `GET /api/companies/{company_id}/sources`
- `GET /api/companies/{company_id}/events`
- `POST /api/proposals/analyze` – placeholder analysis response; Member 3 implements evidence-grounded analysis
- `POST /api/feedback`
- `GET /api/feedback/analysis/{company_id}`

See `docs/API_CONTRACT.md` for payload examples.

## Important

The scaffold does not yet crawl websites, call Ollama, calculate sentiment, or produce validated recommendations. Those are the feature modules the team will implement. The placeholder endpoints must not be presented as completed AI functionality.
