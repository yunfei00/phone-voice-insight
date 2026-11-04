from datetime import date
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.assistant.orchestrator import _time_context


class RelativeDateTests(SimpleTestCase):
    @patch("apps.assistant.orchestrator.timezone.localdate", return_value=date(2026, 11, 4))
    def test_recent_thirty_days(self, _localdate):
        prompt, filters = _time_context("最近30天导航相关的有哪些问题？")
        self.assertEqual(filters, {"start_date": "2026-10-06", "end_date": "2026-11-04"})
        self.assertIn("2026-11-04", prompt)

    @patch("apps.assistant.orchestrator.timezone.localdate", return_value=date(2026, 1, 2))
    def test_cross_year(self, _localdate):
        _, filters = _time_context("近7天有哪些问题")
        self.assertEqual(filters, {"start_date": "2025-12-27", "end_date": "2026-01-02"})
