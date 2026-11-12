import unittest

from app.intelligence.rag import (
    _diversify_internal_results,
    _extract_candidate_claims,
    _classify_sentence_relevance,
    _filter_internal_candidates_by_focus,
    _filter_evidence_by_publication_period,
    _query_focus_phrase,
    _query_focus_terms,
    _requested_publication_period,
    _requested_answer_aspects,
    _claim_covers_exact_date,
    _query_requires_exact_calendar_day,
    _split_sentences,
    _tokens,
    _claim_covers_aspect,
    _is_noise_sentence,
)


class RAGRelevanceTests(unittest.TestCase):
    def setUp(self):
        self.query = "What changes were announced to Spotify Premium Family?"
        self.focus_terms = _query_focus_terms(self.query, "Spotify")
        self.focus_phrase = _query_focus_phrase(self.query, "Spotify")

    def classify(self, sentence, title):
        return _classify_sentence_relevance(
            sentence, title, _tokens(sentence), self.focus_terms, self.focus_phrase
        )[0]

    def test_family_mix_is_direct_match_from_family_upgrade_source(self):
        self.assertEqual(
            self.classify(
                "Family Mix: Families will get exclusive access to a personalized playlist packed with songs the whole family enjoys.",
                "Upgraded Spotify Premium Family Plan: Value the Entire Household Will Love",
            ),
            "direct_match",
        )

    def test_family_hub_is_direct_match_from_family_upgrade_source(self):
        self.assertEqual(
            self.classify(
                "Family Hub: Billing users can now manage their Family's settings in one place, including adding or removing family members.",
                "Upgraded Spotify Premium Family Plan: Value the Entire Household Will Love",
            ),
            "direct_match",
        )

    def test_spotify_kids_is_related_later_development(self):
        self.assertEqual(
            self.classify(
                "Spotify Kids is a standalone app available exclusively for Premium Family subscribers and intended for kids ages 3+.",
                "Introducing Spotify Kids, A New Standalone App",
            ),
            "related_development",
        )

    def test_price_change_is_separate_related_development(self):
        self.assertEqual(
            self.classify(
                "In the United States, the announced Premium Family price was $16.99.",
                "Adjusting Our Spotify Premium Prices",
            ),
            "related_development",
        )

    def test_generic_offline_benefit_is_not_a_family_change(self):
        self.assertEqual(
            self.classify(
                "Offline downloads are included with every Premium plan — Individual, Duo, Family, and Student.",
                "Download Music and Listen Offline | Spotify Premium",
            ),
            "contextual_only",
        )

    def test_2014_family_plan_introduction_is_historical_context(self):
        self.assertEqual(
            self.classify(
                "March 2014: Spotify adds Family and Student plans, because sharing is caring.",
                "Spotify: A Visual History",
            ),
            "related_development",
        )

    def test_month_year_filter(self):
        self.assertEqual(_requested_publication_period("What changed in August 2019?"), (2019, 8))
        evidence = [
            {"publication_date": "2019-08-19T00:00:00"},
            {"publication_date": "2019-10-30T00:00:00"},
            {"publication_date": None},
        ]
        self.assertEqual(
            len(_filter_evidence_by_publication_period(evidence, (2019, 8))), 1
        )

    def test_product_specific_question_does_not_borrow_unrelated_outcome(self):
        evidence = [
            {
                "source_id": "synthetic-price-source",
                "source_title": "Synthetic Orbit Desk Pro pricing",
                "chunk_text": (
                    "Aster Works raised the monthly Orbit Desk Pro price "
                    "from $8 to $10. The announcement did not give a reason "
                    "or report a sales outcome."
                ),
                "similarity": 0.8,
            },
            {
                "source_id": "synthetic-experiment-source",
                "source_title": "Synthetic checkout experiment",
                "chunk_text": (
                    "Aster reported completion increased by 6% during "
                    "the experiment."
                ),
                "similarity": 0.7,
            },
        ]

        claims = _extract_candidate_claims(
            evidence=evidence,
            query=(
                "What sales outcome followed the Orbit Desk Pro price increase?"
            ),
            company_name="Aster Works",
        )

        statements = [claim["statement"] for claim in claims]
        self.assertIn(
            "The announcement did not give a reason or report a sales outcome.",
            statements,
        )
        self.assertNotIn(
            "Aster reported completion increased by 6% during the experiment.",
            statements,
        )

    def test_unilever_footer_about_experience_is_not_a_relevant_claim(self):
        evidence = [
            {
                "source_id": "synthetic-unilever",
                "source_title": "Improved performance | Unilever",
                "chunk_text": (
                    "We would love to hear about your experience using "
                    "Unilever.com. Unilever reported TRESemmé grew "
                    "mid-single digit following the Lamellar Shine launch."
                ),
                "similarity": 0.8,
            }
        ]
        claims = _extract_candidate_claims(
            evidence=evidence,
            query="What did Unilever report about TRESemmé and the Lamellar Shine collection?",
            company_name="Unilever PLC",
        )
        statements = [claim["statement"] for claim in claims]

        self.assertTrue(any("mid-single digit" in statement for statement in statements))
        self.assertFalse(any("love to hear" in statement for statement in statements))

    def test_exact_calendar_day_requires_day_month_and_year(self):
        query = "What exact calendar day did TRESemmé Professional launch?"
        self.assertIn("date", _requested_answer_aspects(query))
        self.assertTrue(_query_requires_exact_calendar_day(query))
        self.assertFalse(_claim_covers_exact_date("It launched in May 2026."))
        self.assertTrue(_claim_covers_exact_date("It launched on May 12, 2026."))
        self.assertTrue(_claim_covers_exact_date("The product launched on July 9, 2026."))
        self.assertFalse(
            _claim_covers_exact_date(
                "Published 9 July 2026. The product launched in May 2026."
            )
        )

    def test_plural_multi_part_question_aspects_are_all_detected(self):
        query = (
            "Which products are described, and what launch dates, "
            "stated reasons, experiments, and reported outcomes are documented?"
        )
        self.assertEqual(
            _requested_answer_aspects(query),
            {"date", "event", "experiment", "outcome", "reason"},
        )
        self.assertEqual(
            _query_focus_terms(query, "Samsung Electronics"),
            set(),
        )

    def test_generic_multi_part_event_question_does_not_filter_relevant_passage(self):
        query = (
            "What feature was introduced, when was it introduced, why was it "
            "added, and what measured outcome was reported?"
        )
        passage = {
            "source_id": "synthetic-event-source",
            "source_title": "[SYNTHETIC DEMO] product event fixture",
            "chunk_text": (
                "SYNTHETIC TEST FIXTURE. On April 14, 2024, the fictional "
                "Aurora Timer feature was introduced to reduce missed "
                "reminders. In a fictional test, missed reminders fell "
                "from 20 percent to 12 percent."
            ),
            "similarity": 0.62,
        }

        self.assertEqual(_query_focus_terms(query, "NEXUS test company"), set())
        self.assertEqual(
            _filter_internal_candidates_by_focus(
                [passage], query=query, company_name="NEXUS test company"
            ),
            [passage],
        )

    def test_internal_retrieval_keeps_source_diversity_and_contradictory_sources(self):
        results = [
            {"source_id": "source-a", "chunk_text": "top chunk", "similarity": 0.91},
            {"source_id": "source-a", "chunk_text": "repeat chunk", "similarity": 0.90},
            {"source_id": "source-a", "chunk_text": "third chunk", "similarity": 0.89},
            {"source_id": "source-b", "chunk_text": "supports claim", "similarity": 0.82},
            {"source_id": "source-c", "chunk_text": "contradicts claim", "similarity": 0.79},
        ]

        selected = _diversify_internal_results(results, limit=3)

        self.assertEqual(
            [item["source_id"] for item in selected],
            ["source-a", "source-b", "source-c"],
        )
        self.assertIn(
            "contradicts claim",
            [item["chunk_text"] for item in selected],
        )

    def test_product_focus_filters_tangential_corporate_sources_before_diversity(self):
        query = (
            "What historical launch dates, reasons, and outcomes are "
            "documented for Samsung Odyssey OLED G8?"
        )
        candidates = [
            {
                "source_id": "corporate",
                "source_title": "Samsung Company Information",
                "chunk_text": (
                    "Samsung is a global company. It changed its business "
                    "strategy in 2020 because it planned to invest more."
                ),
                "similarity": 0.91,
            },
            {
                "source_id": "product",
                "source_title": "Samsung Odyssey OLED G8 monitor",
                "chunk_text": (
                    "Samsung Odyssey OLED G8 monitor product specifications "
                    "describe a display with a 2025 panel."
                ),
                "similarity": 0.62,
            },
            {
                "source_id": "another-product",
                "source_title": "Samsung Galaxy phone",
                "chunk_text": "Samsung Galaxy phones were updated in 2024.",
                "similarity": 0.80,
            },
        ]

        filtered = _filter_internal_candidates_by_focus(
            candidates,
            query=query,
            company_name="Samsung Electronics",
        )
        selected = _diversify_internal_results(filtered, limit=2)

        self.assertEqual([item["source_id"] for item in selected], ["product"])

    def test_page_boilerplate_is_not_a_verified_product_claim_candidate(self):
        evidence = [{
            "source_id": "synthetic-monitor-page",
            "source_title": "Samsung Odyssey OLED G8 monitor",
            "chunk_text": (
                "2026 ENGLISH, ARABIC, FRENCH, PORTUGUESE, THAI, VIETNAMESE "
                "Layer Popup Close Download See more content Solutions & Tips "
                "How to fix if Samsung monitor is not turning ON. "
                "All features, specifications and prices are subject to "
                "change without prior notice."
            ),
            "similarity": 0.9,
        }]
        claims = _extract_candidate_claims(
            evidence,
            "What historical launch date and reported outcome are documented "
            "for Samsung Odyssey OLED G8?",
            "Samsung Electronics",
        )
        self.assertEqual(claims, [])

    def test_date_aspect_requires_date_near_a_documented_product_event(self):
        self.assertTrue(
            _claim_covers_aspect(
                "Samsung announced Odyssey OLED G8 on March 3, 2025.",
                "date",
            )
        )
        self.assertFalse(
            _claim_covers_aspect(
                "The product page is labeled 2026 and lists monitor updates.",
                "date",
            )
        )

    def test_multipart_answer_does_not_include_unrequested_page_facts(self):
        evidence = [{
            "source_id": "synthetic-product-page",
            "source_title": "Synthetic Acme product page",
            "chunk_text": (
                "The product launched on March 3, 2025. "
                "A running coach program is available on Android phones."
            ),
            "similarity": 0.9,
        }]
        claims = _extract_candidate_claims(
            evidence,
            "What product launch date and reported outcome are documented?",
            "Synthetic Acme",
        )
        statements = [claim["statement"] for claim in claims]
        self.assertEqual(
            statements,
            ["The product launched on March 3, 2025."],
        )

    def test_measured_outcome_sentence_survives_noise_filtering(self):
        sentence = (
            "The report stated that the redesigned dashboard reduced the "
            "average time needed to locate a project update from 90 seconds "
            "to 55 seconds."
        )
        self.assertGreater(len(sentence), 100)
        self.assertFalse(_is_noise_sentence(sentence))
        self.assertTrue(_claim_covers_aspect(sentence, "outcome"))

        evidence = [{
            "source_id": "synthetic-experiment-source",
            "source_title": "Synthetic PulseBoard Product Case Study",
            "chunk_text": sentence,
            "similarity": 0.8,
        }]
        claims = _extract_candidate_claims(
            evidence,
            "What outcome was documented?",
            "NEXUS Synthetic Demo",
        )
        self.assertIn(sentence, [claim["statement"] for claim in claims])

    def test_result_label_without_result_does_not_cover_outcome(self):
        self.assertFalse(
            _claim_covers_aspect(
                "The report described this as a result of the fictional experiment.",
                "outcome",
            )
        )
        self.assertTrue(
            _claim_covers_aspect(
                "The announcement did not give a reason or report a sales outcome.",
                "outcome",
            )
        )

    def test_launch_timing_geography_words_do_not_block_event_evidence(self):
        query = "What launch timing and geography are documented for TRESemmé Professional?"
        focus_terms = _query_focus_terms(query, "TRESemmé")
        self.assertFalse(focus_terms.intersection({"timing", "geography", "documented"}))

    def test_product_specific_event_query_excludes_unrelated_date_sentences(self):
        query = "What launch timing and geography are documented for TRESemmé Professional?"
        evidence = [{
            "source_id": "synthetic-tresemme",
            "source_title": "TRESemmé Professional transformation | Unilever",
            "chunk_text": (
                "The premium haircare market is projected to grow from "
                "$128.35 billion in 2026 to $252.95 billion by 2034. "
                "TRESemmé Professional launched in the UK & Ireland in May 2026."
            ),
            "similarity": 0.8,
        }]
        claims = _extract_candidate_claims(evidence, query, "TRESemmé")
        statements = [claim["statement"] for claim in claims]

        self.assertIn(
            "TRESemmé Professional launched in the UK & Ireland in May 2026.",
            statements,
        )
        self.assertFalse(any("premium haircare market" in statement for statement in statements))

    def test_reason_sentence_can_use_product_specific_source_heading(self):
        query = "Why did Orbit Desk change its monthly plan?"
        evidence = [{
            "source_id": "synthetic-orbit",
            "source_title": "Orbit Desk plan update",
            "chunk_text": "The company said the update was designed to improve affordability.",
            "similarity": 0.8,
        }]
        claims = _extract_candidate_claims(evidence, query, "Aster Works")

        self.assertTrue(any("designed to improve affordability" in claim["statement"] for claim in claims))

    def test_candidate_sentence_near_embedding_chunk_limit_is_not_dropped(self):
        sentence = (
            "TRESemmé Professional launched in the UK and Ireland in May 2026, "
            + "with premium salon-quality haircare details " * 17
            + "to support the complete range."
        )
        self.assertGreater(len(sentence), 700)
        self.assertLessEqual(len(sentence), 1200)

        self.assertIn(sentence, _split_sentences(sentence))


if __name__ == "__main__":
    unittest.main(verbosity=2)
