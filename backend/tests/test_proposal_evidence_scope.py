from app.intelligence.proposal_analysis import _build_evidence_message, _validate_model_result


def test_public_company_pages_are_not_labelled_as_internal_history():
    source_id = "synthetic-public-source"
    evidence = [{
        "source_id": source_id,
        "source_company_name": "[SYNTHETIC] Northstar",
        "source_title": "Public product page",
        "source_url": "https://northstar.example/product",
        "evidence_scope": "public_company",
        "chunk_text": "Northstar publicly described its checkout product.",
    }]
    message = _build_evidence_message(evidence)
    assert "EVIDENCE_SCOPE: public_company" in message
    assert "EVIDENCE_SCOPE: internal" not in message

    result = _validate_model_result(
        result={
            "recommendation": "PILOT for [SYNTHETIC] Northstar after validation.",
            "risks": [],
            "limitations": [],
            "claims": [{
                "statement": "Northstar publicly described its checkout product.",
                "type": "factual_observation",
                "source_ids": [source_id],
            }],
        },
        allowed_source_ids={source_id},
        source_provenance={source_id: {
            "evidence_scope": "public_company",
            "source_title": "Public product page",
        }},
        proposing_company_name="[SYNTHETIC] Northstar",
    )
    assert result["claims"][0]["evidence_scope"] == "public_company"
    assert result["claims"][0]["source_provenance"][0]["evidence_scope"] == "public_company"
