from datetime import date
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.assistant.orchestrator import AssistantOrchestrator, _time_context


class RelativeDateTests(SimpleTestCase):
    @patch("apps.assistant.orchestrator.timezone.localdate", return_value=date(2026, 11, 4))
    def test_recent_thirty_days_uses_server_year(self, _localdate: Any) -> None:
        prompt, filters = _time_context("最近30天导航相关的有哪些问题?")
        self.assertEqual(filters, {"start_date": "2026-10-06", "end_date": "2026-11-04"})
        self.assertIn("2026-10-06", prompt)
        self.assertNotIn("2023", prompt)

    @patch("apps.assistant.orchestrator.timezone.localdate", return_value=date(2026, 1, 2))
    def test_cross_year(self, _localdate: Any) -> None:
        _, filters = _time_context("近7天有哪些问题")
        self.assertEqual(filters, {"start_date": "2025-12-27", "end_date": "2026-01-02"})

    @patch("apps.assistant.orchestrator.timezone.localdate", return_value=date(2026, 11, 4))
    def test_fifty_days_is_a_date_range_not_result_limit(self, _localdate: Any) -> None:
        question = "最近五十天有哪些问题,通信相关的"
        # Chinese numerals are a normal customer phrasing, not a tool limit.
        prompt, filters = _time_context(question)
        self.assertEqual(filters, {"start_date": "2026-09-16", "end_date": "2026-11-04"})
        self.assertIn("2026-09-16", prompt)
        name, args = AssistantOrchestrator._fallback_route(AssistantOrchestrator.__new__(AssistantOrchestrator), question, {})
        self.assertEqual(name, "get_issue_statistics")
        self.assertNotIn("limit", args)
