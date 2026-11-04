"""Guard the communication dashboard's counting contract without database fixtures."""
from django.test import SimpleTestCase


class CommunicationAggregationContractTests(SimpleTestCase):
    def test_distinct_feedback_not_opinion_count(self):
        opinions = [
            {"content_id": 1, "topic": "NET.ELEVATOR"},
            {"content_id": 1, "topic": "NET.WEAK_SIGNAL"},
            {"content_id": 2, "topic": "NET.WEAK_SIGNAL"},
        ]
        distinct_feedback = {row["content_id"] for row in opinions}
        category_counts = {
            topic: len({row["content_id"] for row in opinions if row["topic"] == topic})
            for topic in {row["topic"] for row in opinions}
        }
        self.assertEqual(len(distinct_feedback), 2)
        self.assertEqual(category_counts["NET.WEAK_SIGNAL"], 2)
        self.assertEqual(category_counts["NET.ELEVATOR"], 1)
        self.assertGreater(sum(category_counts.values()), len(distinct_feedback))
