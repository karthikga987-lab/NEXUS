
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes import (
    ai,
    companies,
    feedback,
    ingestion,
    knowledge_graph,
    proposals,
)


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


app.include_router(
    companies.router,
    prefix="/api/companies",
    tags=["Companies"],
)

app.include_router(
    knowledge_graph.router,
    prefix="/api/companies",
    tags=["Knowledge Graph"],
)

app.include_router(
    proposals.router,
    prefix="/api/proposals",
    tags=["Proposals"],
)

app.include_router(
    feedback.router,
    prefix="/api/feedback",
    tags=["Feedback"],
)

app.include_router(
    ingestion.router,
    prefix="/api/ingestion",
    tags=["Knowledge Ingestion"],
)

app.include_router(
    ai.router,
    prefix="/api/ai",
    tags=["AI Intelligence"],
)


@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "service": "nexus-api",
    }
