from app.intelligence import embeddings


def test_query_embedding_cache_is_model_scoped_and_normalizes_whitespace(monkeypatch):
    calls = []
    embeddings._cached_query_embedding.cache_clear()
    monkeypatch.setattr(
        embeddings,
        "generate_embeddings",
        lambda texts: (calls.append(list(texts)) or [[0.5, 0.5]]),
    )
    try:
        first = embeddings._query_embedding("  synthetic   product query ")
        second = embeddings._query_embedding("synthetic product query")
        assert first == second == [0.5, 0.5]
        assert calls == [["synthetic product query"]]
    finally:
        embeddings._cached_query_embedding.cache_clear()
