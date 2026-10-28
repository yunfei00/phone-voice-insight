from unittest.mock import MagicMock, patch

from collectors.base import CollectorError
from django.test import SimpleTestCase, override_settings

from apps.sources.services.target_validation import _public_addresses, diagnose_dns


class NetworkDiagnosticsTests(SimpleTestCase):
    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_private_dns_is_reported_and_blocked(self, resolver: MagicMock) -> None:
        resolver.return_value = [(2, 1, 6, "", ("172.31.0.12", 443))]
        report = diagnose_dns("club.honor.com")
        self.assertEqual(report["dns_status"], "SSRF_BLOCKED")
        self.assertEqual(report["blocked_addresses"], ["172.31.0.12"])
        with self.assertRaises(CollectorError):
            _public_addresses("club.honor.com")

    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_public_dns(self, resolver: MagicMock) -> None:
        resolver.return_value = [(2, 1, 6, "", ("93.184.215.14", 443))]
        self.assertEqual(diagnose_dns("club.honor.com")["dns_status"], "PUBLIC")
        self.assertEqual(_public_addresses("club.honor.com"), ["93.184.215.14"])

    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_mixed_dns_is_blocked(self, resolver: MagicMock) -> None:
        resolver.return_value = [
            (2, 1, 6, "", ("93.184.215.14", 443)),
            (2, 1, 6, "", ("172.31.0.12", 443)),
        ]
        self.assertEqual(diagnose_dns("club.honor.com")["dns_status"], "SSRF_BLOCKED")
        with self.assertRaises(CollectorError):
            _public_addresses("club.honor.com")

    @override_settings(SSRF_ALLOWED_HOSTS=["club.honor.com"], SSRF_ALLOWED_PRIVATE_IPS=["172.31.0.12"])
    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_explicit_pinned_enterprise_dns(self, resolver: MagicMock) -> None:
        resolver.return_value = [(2, 1, 6, "", ("172.31.0.12", 443))]
        self.assertEqual(_public_addresses("club.honor.com"), ["172.31.0.12"])
        with self.assertRaises(CollectorError):
            _public_addresses("other.example.com")

    @override_settings(SSRF_ALLOWED_HOSTS=["club.honor.com"], SSRF_ALLOWED_PRIVATE_IPS=["172.31.0.12"])
    @patch("apps.sources.services.target_validation.socket.getaddrinfo")
    def test_unpinned_private_ip_still_blocked(self, resolver: MagicMock) -> None:
        resolver.return_value = [(2, 1, 6, "", ("10.0.0.1", 443))]
        with self.assertRaises(CollectorError):
            _public_addresses("club.honor.com")
