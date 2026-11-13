
from app.intelligence.embeddings import _diversify_external_results


def make_result(
    source_id,
    company_id,
    similarity,
    chunk_index,
    source_url=None,
):
    return {
        "source_id": source_id,
        "source_company_id": company_id,
        "similarity": similarity,
        "chunk_index": chunk_index,
        "chunk_text": f"Evidence passage {source_id}-{chunk_index}",
        "source_url": source_url,
    }


def test_external_results_keep_only_best_chunk_per_source():
    results = [
        make_result("source-a", "company-a", 0.72, 0),
        make_result("source-a", "company-a", 0.85, 1),
        make_result("source-a", "company-a", 0.79, 2),
        make_result("source-b", "company-b", 0.76, 0),
    ]

    selected = _diversify_external_results(results=results, limit=5)

    selected_source_ids = [item["source_id"] for item in selected]

    assert selected_source_ids.count("source-a") == 1

    source_a = next(item for item in selected if item["source_id"] == "source-a")

    assert source_a["chunk_index"] == 1
    assert source_a["similarity"] == 0.85


def test_external_results_respect_limit_after_deduplication():
    results = [
        make_result("source-a", "company-a", 0.90, 0),
        make_result("source-a", "company-a", 0.88, 1),
        make_result("source-b", "company-b", 0.86, 0),
        make_result("source-c", "company-c", 0.84, 0),
    ]

    selected = _diversify_external_results(results=results, limit=2)

    assert len(selected) == 2

    selected_source_ids = [item["source_id"] for item in selected]

    assert len(selected_source_ids) == len(set(selected_source_ids))


def test_external_results_preserve_original_similarity_scores():
    results = [
        make_result("source-a", "company-a", 0.91, 0),
        make_result("source-b", "company-a", 0.83, 0),
        make_result("source-c", "company-b", 0.80, 0),
    ]

    selected = _diversify_external_results(results=results, limit=3)

    original_scores = {
        item["source_id"]: item["similarity"]
        for item in results
    }

    for item in selected:
        assert item["similarity"] == original_scores[item["source_id"]]


def test_external_results_return_empty_list_for_no_candidates():
    selected = _diversify_external_results(results=[], limit=5)

    assert selected == []


def test_external_results_deduplicate_trailing_slash_url_variants():
    results = [
        make_result(
            "source-a",
            "company-a",
            0.78,
            0,
            "https://www.seekingtex.com/",
        ),
        make_result(
            "source-b",
            "company-b",
            0.91,
            1,
            "https://www.seekingtex.com",
        ),
    ]

    selected = _diversify_external_results(results=results, limit=5)

    assert len(selected) == 1
    assert selected[0]["source_id"] == "source-b"
    assert selected[0]["similarity"] == 0.91


def test_external_results_keep_regional_domains_separate():
    results = [
        make_result(
            "source-in",
            "company-in",
            0.88,
            0,
            "https://www.tresemme.in/",
        ),
        make_result(
            "source-com",
            "company-com",
            0.86,
            0,
            "https://www.tresemme.com/",
        ),
    ]

    selected = _diversify_external_results(results=results, limit=5)

    assert len(selected) == 2
    assert {item["source_id"] for item in selected} == {
        "source-in",
        "source-com",
    }


def test_external_results_keep_highest_similarity_across_duplicate_urls():
    results = [
        make_result(
            "source-a",
            "company-a",
            0.75,
            0,
            "https://example.com/product/",
        ),
        make_result(
            "source-b",
            "company-b",
            0.89,
            1,
            "https://example.com/product",
        ),
        make_result(
            "source-c",
            "company-c",
            0.82,
            0,
            "https://another-example.com/product/",
        ),
    ]

    selected = _diversify_external_results(results=results, limit=5)

    assert len(selected) == 2

    example_result = next(
        item for item in selected
        if item["source_id"] in {"source-a", "source-b"}
    )

    assert example_result["source_id"] == "source-b"
    assert example_result["similarity"] == 0.89
