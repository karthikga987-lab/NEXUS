import unittest

from app.intelligence.rag import (
    _classify_sentence_relevance,
    _filter_evidence_by_publication_period,
    _query_focus_phrase,
    _query_focus_terms,
    _requested_publication_period,
    _tokens,
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
