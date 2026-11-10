
import json
import math
import os
import urllib.error
import urllib.request

from sqlalchemy.orm import Session

from app.models import Company, DocumentEmbedding, SourceDocument


OLLAMA_EMBED_URL = "http://localhost:11434/api/embed"
EMBEDDING_MODEL = "nomic-embed-text"

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

ALLOWED_PERMISSION_STATUSES = {"public", "authorized_internal"}

# External evidence below this similarity score is excluded.
# Override with NEXUS_EXTERNAL_MIN_SIMILARITY when needed.
EXTERNAL_MIN_SIMILARITY = float(
    os.getenv("NEXUS_EXTERNAL_MIN_SIMILARITY", "0.60")
)

if not -1.0 <= EXTERNAL_MIN_SIMILARITY <= 1.0:
    raise ValueError(
        "NEXUS_EXTERNAL_MIN_SIMILARITY must be between -1.0 and 1.0."
    )

# Diversity bonuses affect retrieval ordering only. They never change
# the original similarity score returned with an evidence passage.
EXTERNAL_COMPANY_DIVERSITY_BONUS = 0.08
EXTERNAL_SOURCE_DIVERSITY_BONUS = 0.02


class EmbeddingError(Exception):
    """Raised when embedding generation or storage fails."""


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, preferably at word boundaries."""

    if not text or not text.strip():
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "overlap must be non-negative and smaller than chunk_size."
        )

    text = " ".join(text.split())
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = text.rfind(" ", start, end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(end - overlap, start + 1)

    return chunks


def generate_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using the local Ollama API."""

    if not texts:
        return []

    payload = {
        "model": EMBEDDING_MODEL,
        "input": texts,
    }

    request = urllib.request.Request(
        OLLAMA_EMBED_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.URLError as exc:
        raise EmbeddingError(
            f"Could not connect to Ollama at {OLLAMA_EMBED_URL}: {exc}"
        ) from exc

    except (json.JSONDecodeError, TimeoutError) as exc:
        raise EmbeddingError(
            f"Invalid or timed-out Ollama response: {exc}"
        ) from exc

    vectors = result.get("embeddings")

    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise EmbeddingError(
            "Ollama returned an unexpected embedding response."
        )

    validated_vectors = []

    for vector in vectors:
        if not isinstance(vector, list) or not vector:
            raise EmbeddingError(
                "Ollama returned an empty or invalid vector."
            )

        try:
            validated = [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise EmbeddingError(
                "Embedding contains non-numeric values."
            ) from exc

        if not all(math.isfinite(value) for value in validated):
            raise EmbeddingError(
                "Embedding contains non-finite values."
            )

        validated_vectors.append(validated)

    dimensions = len(validated_vectors[0])

    if any(len(vector) != dimensions for vector in validated_vectors):
        raise EmbeddingError(
            "Embedding dimensions are inconsistent."
        )

    return validated_vectors


def embed_source(
    db: Session,
    source_id: str,
) -> dict:
    """Chunk, embed, and persist one permitted source document."""

    source = db.get(SourceDocument, source_id)

    if source is None:
        raise ValueError(f"Source document not found: {source_id}")

    if source.permission_status not in ALLOWED_PERMISSION_STATUSES:
        raise ValueError(
            f"Source cannot be embedded: permission status is "
            f"'{source.permission_status}'."
        )

    if not source.content_text or not source.content_text.strip():
        raise ValueError("Source document has no content to embed.")

    chunks = chunk_text(source.content_text)

    if not chunks:
        raise ValueError("No usable text chunks were produced.")

    vectors = generate_embeddings(chunks)

    try:
        db.query(DocumentEmbedding).filter(
            DocumentEmbedding.source_id == source_id,
            DocumentEmbedding.model_name == EMBEDDING_MODEL,
        ).delete(synchronize_session=False)

        records = [
            DocumentEmbedding(
                source_id=source_id,
                chunk_index=index,
                chunk_text=chunk,
                embedding=vector,
                model_name=EMBEDDING_MODEL,
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]

        db.add_all(records)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return {
        "source_id": source_id,
        "chunks_created": len(records),
        "embedding_dimensions": len(vectors[0]),
        "model": EMBEDDING_MODEL,
    }


def cosine_similarity(
    vector_a: list[float],
    vector_b: list[float],
) -> float:
    """Calculate cosine similarity between two vectors."""

    if len(vector_a) != len(vector_b):
        raise ValueError(
            "Cannot compare vectors with different dimensions."
        )

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b))

    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def search_similar_chunks(
    db: Session,
    query: str,
    company_id: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Retrieve permitted document chunks ranked by semantic similarity."""

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if limit <= 0:
        raise ValueError("limit must be positive.")

    query_vector = generate_embeddings([query.strip()])[0]

    db_query = (
        db.query(DocumentEmbedding, SourceDocument)
        .join(
            SourceDocument,
            DocumentEmbedding.source_id == SourceDocument.id,
        )
        .filter(
            DocumentEmbedding.model_name == EMBEDDING_MODEL,
            SourceDocument.permission_status.in_(
                ALLOWED_PERMISSION_STATUSES
            ),
        )
    )

    if company_id:
        db_query = db_query.filter(
            SourceDocument.company_id == company_id
        )

    results = []

    for embedding_record, source in db_query.all():
        score = cosine_similarity(
            query_vector,
            embedding_record.embedding,
        )

        results.append({
            "source_id": source.id,
            "source_title": source.title,
            "source_url": source.url,
            "chunk_index": embedding_record.chunk_index,
            "chunk_text": embedding_record.chunk_text,
            "similarity": score,
        })

    results.sort(
        key=lambda item: item["similarity"],
        reverse=True,
    )

    return results[:limit]


def _diversify_external_results(
    results: list[dict],
    limit: int,
) -> list[dict]:
    """
    Apply soft company and source diversity to external retrieval.

    A company receives a one-time ranking bonus until it has contributed
    a result. A source receives a smaller one-time bonus until it has
    contributed a chunk.

    This is a soft preference, not a quota. Original similarity scores
    are preserved, and strongly more relevant evidence can still rank
    ahead of less relevant evidence.
    """

    remaining = list(results)
    selected = []

    represented_companies = set()
    represented_sources = set()

    while remaining and len(selected) < limit:

        def adjusted_score(item: dict) -> tuple[float, float]:
            company_id = item["source_company_id"]
            source_id = item["source_id"]
            similarity = item["similarity"]

            company_bonus = (
                EXTERNAL_COMPANY_DIVERSITY_BONUS
                if company_id not in represented_companies
                else 0.0
            )

            source_bonus = (
                EXTERNAL_SOURCE_DIVERSITY_BONUS
                if source_id not in represented_sources
                else 0.0
            )

            return (
                similarity + company_bonus + source_bonus,
                similarity,
            )

        best_index = max(
            range(len(remaining)),
            key=lambda index: adjusted_score(remaining[index]),
        )

        chosen = remaining.pop(best_index)
        selected.append(chosen)

        represented_companies.add(
            chosen["source_company_id"]
        )
        represented_sources.add(
            chosen["source_id"]
        )

    return selected


def search_external_public_chunks(
    db: Session,
    query: str,
    exclude_company_id: str,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve relevant public historical evidence from other companies.

    Only public sources from other companies are eligible. Results below
    EXTERNAL_MIN_SIMILARITY are excluded before company/source diversity
    ranking. Original similarity scores are preserved.
    """

    if not query or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if not exclude_company_id:
        raise ValueError("The proposing company ID is required.")

    if limit <= 0:
        raise ValueError("limit must be positive.")

    query_vector = generate_embeddings([query.strip()])[0]

    db_query = (
        db.query(DocumentEmbedding, SourceDocument, Company)
        .join(
            SourceDocument,
            DocumentEmbedding.source_id == SourceDocument.id,
        )
        .join(
            Company,
            SourceDocument.company_id == Company.id,
        )
        .filter(
            DocumentEmbedding.model_name == EMBEDDING_MODEL,
            SourceDocument.permission_status == "public",
            SourceDocument.company_id != exclude_company_id,
        )
    )

    results = []

    for embedding_record, source, source_company in db_query.all():
        score = cosine_similarity(
            query_vector,
            embedding_record.embedding,
        )

        # Exclude weakly related external evidence before diversification.
        if score < EXTERNAL_MIN_SIMILARITY:
            continue

        results.append({
            "source_id": source.id,
            "source_title": source.title,
            "source_url": source.url,
            "source_company_id": source_company.id,
            "source_company_name": source_company.name,
            "source_company_industry": source_company.industry,
            "chunk_index": embedding_record.chunk_index,
            "chunk_text": embedding_record.chunk_text,
            "similarity": score,
            "evidence_scope": "external_public",
            "permission_status": source.permission_status,
        })

    return _diversify_external_results(
        results=results,
        limit=limit,
    )
