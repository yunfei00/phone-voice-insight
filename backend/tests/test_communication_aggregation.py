from django.test import SimpleTestCase


class CommunicationCountingContractTests(SimpleTestCase):
    def test_distinct_feedback_counts(self):
        opinions = [(1, "NET.ELEVATOR"), (1, "NET.WEAK_SIGNAL"), (2, "NET.WEAK_SIGNAL")]
        total = len({content_id for content_id, _ in opinions})
        counts = {topic: len({content_id for content_id, tag in opinions if tag == topic}) for _, topic in opinions}
        self.assertEqual(total, 2)
        self.assertEqual(counts["NET.WEAK_SIGNAL"], 2)
        self.assertGreater(sum(counts.values()), total)
