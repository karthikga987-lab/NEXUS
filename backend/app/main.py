from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.init_db import init_db
from app.api.routes import companies, proposals, feedback

app = FastAPI(
    title="NEXUS API",
    description="Shared API for the NEXUS product intelligence platform.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_db()

app.include_router(companies.router, prefix="/api/companies", tags=["Companies"])
app.include_router(proposals.router, prefix="/api/proposals", tags=["Proposals"])
app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])

@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": "nexus-api"}
