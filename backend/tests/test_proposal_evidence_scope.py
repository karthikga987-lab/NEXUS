from app.intelligence import proposal_analysis
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


def test_competitor_excerpt_cannot_cite_unsupported_milton_feature(monkeypatch):
    source_id = "synthetic-gorilla-bottle"
    source_url = "https://example.test/synthetic/gorilla-bottle"
    excerpt = (
        "Synthetic fixture only: Gorilla Wear's insulated bottle has a "
        "temperature display."
    )
    chunk = {
        "source_id": source_id,
        "source_title": "Synthetic Gorilla Wear bottle fixture",
        "source_url": source_url,
        "source_company_id": "synthetic-competitor-id",
        "source_company_name": "Gorilla Wear",
        "proposing_company_id": "milton-id",
        "chunk_text": excerpt,
        "permission_status": "public",
        "evidence_scope": "external_public",
    }
    verifier_input = {}

    monkeypatch.setattr(
        proposal_analysis,
        "_classify_external_passages_with_qwen",
        lambda *args, **kwargs: {"classifications": [{
            "index": 0,
            "category": "competitor_context",
            "proposal_aspect": "temperature display",
            "reason": "Synthetic competitor example, not Milton history.",
        }]},
    )
    monkeypatch.setattr(
        proposal_analysis,
        "_call_ollama_json",
        lambda *args, **kwargs: {
            "recommendation": "PILOT for Milton after validating demand.",
            "risks": [],
            "limitations": [],
            "claims": [{
                "statement": "Milton developed a smart temperature display bottle.",
                "type": "factual_observation",
                "source_ids": [source_id],
            }],
        },
    )

    def reject_claims(claims, source_text_by_id, source_context_by_id):
        verifier_input["claims"] = claims
        verifier_input["passage"] = source_text_by_id[source_id][0]
        verifier_input["company"] = source_context_by_id[source_id]["source_company_name"]
        return {}, None

    monkeypatch.setattr(proposal_analysis, "verify_claim_citations", reject_claims)
    result = proposal_analysis.analyze_proposal_with_evidence(
        title="Milton ThermoSmart bottle",
        description="Hypothetical temperature display drinkware proposal.",
        evidence_chunks=[],
        external_evidence_chunks=[chunk],
        proposing_company_name="Milton",
    )

    assert verifier_input["claims"][0]["candidate_source_ids"] == [source_id]
    assert verifier_input["passage"] == excerpt
    assert verifier_input["company"] == "Gorilla Wear"
    claim = result["claims"][0]
    assert claim["source_ids"] == []
    assert claim["evidence_status"] == "unsupported"
    assert claim["type"] == "hypothesis"
    assert result["evidence_sources"][0]["source_id"] == source_id
    assert result["evidence_sources"][0]["source_url"] == source_url
