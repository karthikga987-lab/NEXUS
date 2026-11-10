import pytest

from app.intelligence import embeddings


def test_chunk_text_returns_empty_for_empty_input():
    assert embeddings.chunk_text("") == []
    assert embeddings.chunk_text("   ") == []


def test_chunk_text_normalizes_whitespace():
    result = embeddings.chunk_text("Hello   world.\nThis is NEXUS.")

    assert result == ["Hello world. This is NEXUS."]


def test_chunk_text_creates_overlapping_chunks():
    text = "one two three four five six seven eight nine ten"

    chunks = embeddings.chunk_text(
        text,
        chunk_size=20,
        overlap=5,
    )

    assert len(chunks) > 1
    assert all(chunks)
    assert all(len(chunk) <= 20 for chunk in chunks)


def test_chunk_text_rejects_invalid_chunk_size():
    with pytest.raises(ValueError):
        embeddings.chunk_text("Some text", chunk_size=0)


def test_chunk_text_rejects_invalid_overlap():
    with pytest.raises(ValueError):
        embeddings.chunk_text("Some text", chunk_size=10, overlap=10)


def test_generate_embeddings_returns_empty_for_empty_input(monkeypatch):
    def unexpected_call(*args, **kwargs):
        raise AssertionError("Ollama should not be called")

    monkeypatch.setattr(
        embeddings.urllib.request,
        "urlopen",
        unexpected_call,
    )

    assert embeddings.generate_embeddings([]) == []



def test_generate_embeddings_validates_response(monkeypatch):
    import json

    vectors = [
        [0.1] * embeddings.EMBEDDING_DIMENSIONS,
        [0.2] * embeddings.EMBEDDING_DIMENSIONS,
    ]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps({"embeddings": vectors}).encode("utf-8")

    monkeypatch.setattr(
        embeddings.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    result = embeddings.generate_embeddings(["first", "second"])

    assert result == vectors
    assert len(result) == 2
    assert all(len(vector) == 768 for vector in result)



@pytest.mark.parametrize(
    "response",
    [
        b'{"embeddings": []}',
        b'{"embeddings": [[0.1]]}',
        b'{"embeddings": [[0.1], [0.2, 0.3]]}',
        b'{"embeddings": [["invalid"]]}',
        b'{"embeddings": [[NaN]]}',
        b'not-json',
    ],
)
def test_generate_embeddings_rejects_invalid_responses(
    monkeypatch,
    response,
):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return response

    monkeypatch.setattr(
        embeddings.urllib.request,
        "urlopen",
        lambda *args, **kwargs: FakeResponse(),
    )

    with pytest.raises(embeddings.EmbeddingError):
        embeddings.generate_embeddings(["first"])


def test_cosine_similarity_identical_vectors():
    result = embeddings.cosine_similarity(
        [1.0, 0.0],
        [1.0, 0.0],
    )

    assert result == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors():
    result = embeddings.cosine_similarity(
        [1.0, 0.0],
        [0.0, 1.0],
    )

    assert result == pytest.approx(0.0)


def test_cosine_similarity_opposite_vectors():
    result = embeddings.cosine_similarity(
        [1.0, 0.0],
        [-1.0, 0.0],
    )

    assert result == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector():
    result = embeddings.cosine_similarity(
        [0.0, 0.0],
        [1.0, 0.0],
    )

    assert result == 0.0


def test_cosine_similarity_rejects_different_dimensions():
    with pytest.raises(ValueError):
        embeddings.cosine_similarity(
            [1.0, 0.0],
            [1.0, 0.0, 0.0],
        )
