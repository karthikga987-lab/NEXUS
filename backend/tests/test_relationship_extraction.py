
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.intelligence.relationship_extraction import (
    extract_and_persist_relationships,
    validate_relationship_candidate,
)
from app.knowledge_graph.builder import build_company_graph
from app.models.entities import (
    Company,
    EventRelationship,
    Proposal,
    ProposalAnalysis,
    ProductEvent,
    ResearchRun,
    SourceDocument,
    event_sources,
    relationship_sources,
)


SOURCE_TEXT = (
    "Spotify introduced Family Mix for Premium Family members. "
    "The feature creates a shared playlist based on members' "
    "listening preferences. The plan resulted in the introduction "
    "of Family Mix."
)

SUPPORTING_QUOTE = "The plan resulted in the introduction of Family Mix."

EVENT_IDS = {
    "event-family-mix",
    "event-family-plan",
}


def make_candidate(**overrides):
    candidate = {
        "from_event_id": "event-family-plan",
        "to_event_id": "event-family-mix",
        "relation_type": "RESULTED_IN",
        "evidence_status": "supported_relationship",
        "confidence": 0.95,
        "supporting_quote": SUPPORTING_QUOTE,
        "explanation": "The source describes the introduction.",
    }

    candidate.update(overrides)
    return candidate


class RelationshipExtractionTests(unittest.TestCase):

    def test_valid_relationship_is_accepted(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(error)
        self.assertIsNotNone(validated)
        self.assertEqual(
            validated["relation_type"],
            "RESULTED_IN",
        )
        self.assertEqual(
            validated["evidence_status"],
            "supported_relationship",
        )
        self.assertEqual(
            validated["supporting_quote"],
            SUPPORTING_QUOTE,
        )

    def test_fabricated_quote_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                supporting_quote=(
                    "Spotify launched Family Mix after customer testing."
                )
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(
            error,
            "supporting_quote_not_found_exactly",
        )

    def test_temporal_sequence_does_not_support_causal_relationship(self):
        quote = "Spotify introduced Family Mix after the plan update."
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                relation_type="MOTIVATED_BY",
                supporting_quote=quote,
            ),
            event_ids=EVENT_IDS,
            source_text=quote,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "causal_relationship_not_explicit")

    def test_invalid_relationship_type_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                relation_type="CAUSED_BY",
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "invalid_relationship_type")

    def test_unknown_relationship_is_not_persistable(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                evidence_status="unknown",
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(
            error,
            "unknown_relationship_not_persisted",
        )

    def test_invalid_evidence_status_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                evidence_status="documented",
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "invalid_evidence_status")

    def test_unknown_event_id_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                to_event_id="event-does-not-exist",
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "to_event_not_in_source")

    def test_self_relationship_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                to_event_id="event-family-plan",
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(
            error,
            "self_relationship_not_allowed",
        )

    def test_confidence_above_one_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(confidence=1.5),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "confidence_out_of_range")

    def test_negative_confidence_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(confidence=-0.1),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "confidence_out_of_range")

    def test_boolean_confidence_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(confidence=True),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "invalid_confidence")

    def test_missing_quote_is_rejected(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(supporting_quote=""),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(validated)
        self.assertEqual(error, "missing_supporting_quote")

    def test_same_quote_is_used_as_persisted_explanation(self):
        validated, error = validate_relationship_candidate(
            candidate=make_candidate(
                explanation="An unsupported model-generated explanation."
            ),
            event_ids=EVENT_IDS,
            source_text=SOURCE_TEXT,
        )

        self.assertIsNone(error)
        self.assertEqual(
            validated["explanation"],
            validated["supporting_quote"],
        )


class RelationshipPersistenceTests(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")

        required_tables = [
            Company.__table__,
            ResearchRun.__table__,
            Proposal.__table__,
            ProposalAnalysis.__table__,
            ProductEvent.__table__,
            SourceDocument.__table__,
            EventRelationship.__table__,
            event_sources,
            relationship_sources,
        ]

        Base.metadata.create_all(
            self.engine,
            tables=required_tables,
        )

        self.Session = sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
        )

        self.db = self.Session()

        self.company = Company(
            name="Spotify Test Company",
            website="https://www.spotify.com",
        )

        self.db.add(self.company)
        self.db.flush()

        self.family_plan = ProductEvent(
            company_id=self.company.id,
            product_name="Spotify Premium Family",
            event_type="product_update",
            title="Premium Family plan",
            description="Spotify Premium Family plan.",
        )

        self.family_mix = ProductEvent(
            company_id=self.company.id,
            product_name="Spotify Premium Family",
            event_type="feature_introduction",
            title="Family Mix introduction",
            description="Family Mix shared playlist feature.",
        )

        self.source = SourceDocument(
            company_id=self.company.id,
            url=(
                "https://newsroom.spotify.com/"
                "test-family-mix"
            ),
            title="Spotify introduces Family Mix",
            publisher="Spotify Newsroom",
            source_type="press_release",
            content_text=SOURCE_TEXT,
            permission_status="public",
            processing_status="completed",
        )

        self.db.add_all(
            [
                self.family_plan,
                self.family_mix,
                self.source,
            ]
        )
        self.db.flush()

        self.db.execute(
            event_sources.insert(),
            [
                {
                    "event_id": self.family_plan.id,
                    "source_id": self.source.id,
                },
                {
                    "event_id": self.family_mix.id,
                    "source_id": self.source.id,
                },
            ],
        )

        self.db.commit()

        self.candidate = make_candidate(
            from_event_id=self.family_plan.id,
            to_event_id=self.family_mix.id,
        )

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(
            self.engine,
            tables=[
                relationship_sources,
                event_sources,
                EventRelationship.__table__,
            ProposalAnalysis.__table__,
            Proposal.__table__,
                ProductEvent.__table__,
                SourceDocument.__table__,
                ResearchRun.__table__,
                Company.__table__,
            ],
        )
        self.engine.dispose()

    def _run_mocked_extraction(self):
        with (
            patch(
                "app.intelligence.relationship_extraction._ask_ollama",
                return_value=[self.candidate],
            ),
            patch(
                "app.intelligence.relationship_extraction."
                "_verify_relationship_semantics",
                return_value=(
                    True,
                    "semantic_verification_passed",
                ),
            ),
        ):
            return extract_and_persist_relationships(
                db=self.db,
                company_id=self.company.id,
            )

    def test_relationship_and_provenance_are_persisted(self):
        result = self._run_mocked_extraction()

        self.db.commit()

        self.assertEqual(result["relationships_created"], 1)
        self.assertEqual(result["provenance_records_created"], 1)
        self.assertTrue(result["source_provenance_persisted"])

        relationship = (
            self.db.query(EventRelationship)
            .filter(
                EventRelationship.company_id == self.company.id
            )
            .one()
        )

        self.assertEqual(
            relationship.relationship_type,
            "RESULTED_IN",
        )
        self.assertEqual(
            relationship.evidence_status,
            "supported_relationship",
        )
        self.assertEqual(
            relationship.from_event_id,
            self.family_plan.id,
        )
        self.assertEqual(
            relationship.to_event_id,
            self.family_mix.id,
        )

        provenance = self.db.execute(
            select(relationship_sources).where(
                relationship_sources.c.relationship_id
                == relationship.id
            )
        ).mappings().one()

        self.assertEqual(
            provenance["source_id"],
            self.source.id,
        )
        self.assertEqual(
            provenance["supporting_quote"],
            SUPPORTING_QUOTE,
        )
        self.assertEqual(
            provenance["verification_method"],
            "ollama_semantic_verification_v1",
        )

    def test_graph_exposes_persisted_relationship_provenance(self):
        result = self._run_mocked_extraction()
        self.db.commit()

        self.assertEqual(result["provenance_records_created"], 1)

        graph = build_company_graph(
            db=self.db,
            company_id=self.company.id,
        )

        relationship = (
            self.db.query(EventRelationship)
            .filter(
                EventRelationship.company_id == self.company.id
            )
            .one()
        )

        edge = graph.get_edge_data(
            f"event:{self.family_plan.id}",
            f"event:{self.family_mix.id}",
            key=relationship.id,
        )

        self.assertIsNotNone(edge)
        self.assertTrue(edge["source_provenance_available"])
        self.assertEqual(
            edge["supporting_source_ids"],
            [self.source.id],
        )

        supporting_source = edge["supporting_sources"][0]

        self.assertEqual(
            supporting_source["supporting_quote"],
            SUPPORTING_QUOTE,
        )
        self.assertEqual(
            supporting_source["source_url"],
            self.source.url,
        )
        self.assertEqual(
            supporting_source["publisher"],
            "Spotify Newsroom",
        )
        self.assertEqual(
            supporting_source["verification_method"],
            "ollama_semantic_verification_v1",
        )

    def test_repeated_extraction_does_not_duplicate_provenance(self):
        first_result = self._run_mocked_extraction()
        self.db.commit()

        second_result = self._run_mocked_extraction()
        self.db.commit()

        self.assertEqual(first_result["relationships_created"], 1)
        self.assertEqual(first_result["provenance_records_created"], 1)

        self.assertEqual(second_result["relationships_created"], 0)
        self.assertEqual(second_result["provenance_records_created"], 0)

        relationship_count = (
            self.db.query(EventRelationship)
            .filter(
                EventRelationship.company_id == self.company.id
            )
            .count()
        )

        provenance_count = self.db.execute(
            select(relationship_sources.c.relationship_id)
        ).all()

        self.assertEqual(relationship_count, 1)
        self.assertEqual(len(provenance_count), 1)


if __name__ == "__main__":
    unittest.main()
