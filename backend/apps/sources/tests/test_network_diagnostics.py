from unittest.mock import patch

from django.test import SimpleTestCase

from apps.sources.services.target_validation import _public_addresses, diagnose_dns
from collectors.base import CollectorError


class NetworkDiagnosticsTests(SimpleTestCase):
    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_private_dns_is_reported_and_blocked(self, resolver):
        resolver.return_value = [(2, 1, 6, "", ("172.31.0.12", 443))]
        report = diagnose_dns("club.honor.com")
        self.assertEqual(report["dns_status"], "SSRF_BLOCKED")
        self.assertEqual(report["blocked_addresses"], ["172.31.0.12"])
        with self.assertRaises(CollectorError):
            _public_addresses("club.honor.com")

    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_public_dns(self, resolver):
        resolver.return_value = [(2, 1, 6, "", ("93.184.215.14", 443))]
        self.assertEqual(diagnose_dns("club.honor.com")["dns_status"], "PUBLIC")
        self.assertEqual(_public_addresses("club.honor.com"), ["93.184.215.14"])

    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_mixed_dns_is_blocked(self, resolver):
        resolver.return_value = [
            (2, 1, 6, "", ("93.184.215.14", 443)),
            (2, 1, 6, "", ("172.31.0.12", 443)),
        ]
        self.assertEqual(diagnose_dns("club.honor.com")["dns_status"], "SSRF_BLOCKED")
        with self.assertRaises(CollectorError):
            _public_addresses("club.honor.com")
