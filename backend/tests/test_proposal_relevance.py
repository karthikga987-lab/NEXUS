
import pytest

from app.intelligence.proposal_relevance import (
    classify_external_passage_relevance,
    filter_external_passages,
)


def test_relevant_haircare_passage_is_direct_match():
    result = classify_external_passage_relevance(
        title="Scalp Care and Hair Repair Shampoo",
        description=(
            "A shampoo range designed for scalp care, "
            "hair repair, frizz reduction and breakage."
        ),
        passage=(
            "The company introduced a shampoo with scalp care "
            "ingredients designed to reduce hair breakage and frizz."
        ),
    )

    assert result["category"] == "direct_match"
    assert "shampoo" in result["overlap_terms"]
    assert "scalp" in result["overlap_terms"]


def test_relevant_cross_industry_passage_is_retained():
    result = classify_external_passage_relevance(
        title="Sustainable Packaging Proposal",
        description=(
            "Develop recyclable packaging to reduce plastic waste "
            "and improve material sustainability."
        ),
        passage=(
            "A food manufacturer redesigned its packaging using "
            "recyclable materials to reduce plastic waste."
        ),
    )

    assert result["category"] == "direct_match"


def test_unrelated_apparel_passage_is_excluded():
    result = classify_external_passage_relevance(
        title="Scalp Care and Hair Repair Shampoo",
        description=(
            "A shampoo range designed for scalp care, "
            "hair repair, frizz reduction and breakage."
        ),
        passage=(
            "The apparel company launched compression leggings "
            "with breathable fabric and four-way stretch."
        ),
    )

    assert result["category"] == "unrelated"


def test_unrelated_technology_passage_is_excluded():
    result = classify_external_passage_relevance(
        title="Scalp Care and Hair Repair Shampoo",
        description=(
            "A shampoo range designed for scalp care, "
            "hair repair, frizz reduction and breakage."
        ),
        passage=(
            "The technology company announced a cloud computing "
            "platform with improved database performance."
        ),
    )

    assert result["category"] == "unrelated"


def test_empty_passage_is_unrelated():
    result = classify_external_passage_relevance(
        title="Scalp Care Shampoo",
        description="Shampoo for scalp care and hair repair.",
        passage="",
    )

    assert result["category"] == "unrelated"
    assert result["overlap_count"] == 0


def test_filter_preserves_original_source_metadata():
    original = {
        "source_id": "source-123",
        "source_title": "Hair Care Research",
        "source_url": "https://example.com/hair-care",
        "chunk_text": (
            "The shampoo supports scalp care and hair repair."
        ),
        "similarity": 0.82,
    }

    accepted, excluded = filter_external_passages(
        title="Scalp Care Shampoo",
        description="A shampoo for scalp care and hair repair.",
        passages=[original],
    )

    assert len(accepted) == 1
    assert excluded == []

    assert accepted[0]["source_id"] == "source-123"
    assert accepted[0]["source_url"] == original["source_url"]
    assert accepted[0]["similarity"] == 0.82

    assert "proposal_relevance" not in original


def test_filter_separates_relevant_and_unrelated_passages():
    passages = [
        {
            "source_id": "relevant-1",
            "chunk_text": (
                "The shampoo formula supports scalp care "
                "and reduces hair breakage."
            ),
        },
        {
            "source_id": "unrelated-1",
            "chunk_text": (
                "The company sells compression leggings "
                "made from breathable fabric."
            ),
        },
    ]

    accepted, excluded = filter_external_passages(
        title="Scalp Care Shampoo",
        description=(
            "A shampoo range for scalp care and hair repair."
        ),
        passages=passages,
    )

    assert [item["source_id"] for item in accepted] == ["relevant-1"]
    assert [item["source_id"] for item in excluded] == ["unrelated-1"]
    assert excluded[0]["proposal_relevance"] == "unrelated"


def test_qwen_filter_accepts_only_direct_matches():
    passages = [
        {"source_id": "direct", "chunk_text": "Hair repair shampoo."},
        {"source_id": "context", "chunk_text": "Hair finishing oil."},
        {"source_id": "unrelated", "chunk_text": "Industrial fabric."},
        {"source_id": "unknown", "chunk_text": ""},
    ]

    def fake_classifier(title, description, batch):
        return {
            "classifications": [
                {
                    "index": 0,
                    "category": "direct_match",
                    "reason": "Same shampoo product category.",
                },
                {
                    "index": 1,
                    "category": "contextual",
                    "reason": "Related haircare product, but not shampoo.",
                },
                {
                    "index": 2,
                    "category": "unrelated",
                    "reason": "Industrial fabric is unrelated.",
                },
                {
                    "index": 3,
                    "category": "insufficient_information",
                    "reason": "No useful passage content.",
                },
            ]
        }

    accepted, excluded = filter_external_passages(
        title="Hair Repair Shampoo",
        description="A shampoo for hair repair.",
        passages=passages,
        classifier=fake_classifier,
        batch_size=4,
    )

    assert [item["source_id"] for item in accepted] == ["direct"]

    assert {
        item["source_id"] for item in excluded
    } == {"context", "unrelated", "unknown"}

    assert all(
        item["proposal_relevance_method"] == "qwen"
        for item in accepted + excluded
    )


def test_qwen_filter_preserves_source_metadata_without_mutation():
    original = {
        "source_id": "source-123",
        "source_url": "https://example.com/shampoo",
        "similarity": 0.91,
        "chunk_text": "Hair repair shampoo.",
    }

    def fake_classifier(title, description, batch):
        return {
            "classifications": [
                {
                    "index": 0,
                    "category": "direct_match",
                    "reason": "Direct shampoo category match.",
                }
            ]
        }

    accepted, excluded = filter_external_passages(
        title="Hair Repair Shampoo",
        description="A shampoo for hair repair.",
        passages=[original],
        classifier=fake_classifier,
    )

    assert len(accepted) == 1
    assert excluded == []

    assert accepted[0]["source_id"] == "source-123"
    assert accepted[0]["source_url"] == original["source_url"]
    assert accepted[0]["similarity"] == 0.91

    assert accepted[0]["proposal_relevance"] == "direct_match"
    assert accepted[0]["proposal_relevance_method"] == "qwen"

    assert "proposal_relevance" not in original


def test_qwen_filter_excludes_batch_when_classifier_fails():
    passages = [
        {"source_id": "one", "chunk_text": "Hair repair shampoo."},
        {"source_id": "two", "chunk_text": "Scalp care shampoo."},
    ]

    def failing_classifier(title, description, batch):
        raise TimeoutError("Simulated Qwen timeout")

    accepted, excluded = filter_external_passages(
        title="Hair Repair Shampoo",
        description="A shampoo for scalp care and hair repair.",
        passages=passages,
        classifier=failing_classifier,
        batch_size=4,
    )

    assert accepted == []
    assert len(excluded) == 2

    assert all(
        item["proposal_relevance"] == "classification_failed"
        for item in excluded
    )

    assert all(
        "Simulated Qwen timeout" in item["proposal_relevance_reason"]
        for item in excluded
    )


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"classifications": []},
        {
            "classifications": [
                {
                    "index": 0,
                    "category": "unknown_category",
                    "reason": "Invalid category.",
                }
            ]
        },
        {
            "classifications": [
                {
                    "index": 0,
                    "category": "direct_match",
                    "reason": "",
                }
            ]
        },
        {
            "classifications": [
                {
                    "index": 0,
                    "category": "direct_match",
                    "reason": "Valid entry.",
                },
                {
                    "index": 0,
                    "category": "unrelated",
                    "reason": "Duplicate index.",
                },
            ]
        },
    ],
)
def test_qwen_filter_fails_closed_on_invalid_responses(response):
    passages = [
        {"source_id": "one", "chunk_text": "Hair repair shampoo."}
    ]

    def malformed_classifier(title, description, batch):
        return response

    accepted, excluded = filter_external_passages(
        title="Hair Repair Shampoo",
        description="A shampoo for hair repair.",
        passages=passages,
        classifier=malformed_classifier,
    )

    assert accepted == []
    assert len(excluded) == 1
    assert excluded[0]["proposal_relevance"] == "classification_failed"


def test_qwen_filter_processes_passages_in_separate_batches():
    passages = [
        {"source_id": str(index), "chunk_text": f"Passage {index}"}
        for index in range(6)
    ]

    observed_batch_sizes = []

    def fake_classifier(title, description, batch):
        observed_batch_sizes.append(len(batch))

        return {
            "classifications": [
                {
                    "index": index,
                    "category": "direct_match",
                    "reason": "Direct match for this test.",
                }
                for index, _ in enumerate(batch)
            ]
        }

    accepted, excluded = filter_external_passages(
        title="Test proposal",
        description="Test description.",
        passages=passages,
        classifier=fake_classifier,
        batch_size=4,
    )

    assert observed_batch_sizes == [4, 2]
    assert len(accepted) == 6
    assert excluded == []
