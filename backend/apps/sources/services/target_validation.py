"""荣耀俱乐部采集入口的小流量验证与 SSRF 防护。"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

from collectors.base import CollectorError
from collectors.honor_club.client import HonorClubClient, validate_honor_url
from collectors.honor_club.normalizer import normalize_match_text
from collectors.honor_club.parser import extract_topic_identity, is_valid_topic_page, parse_topic_page
from django.conf import settings
from django.utils import timezone

from apps.sources.models import SourceTarget, TargetValidationStatus

_TOPIC_ID = re.compile(r"/threadtopic-(?P<topic_id>\d+)-\d+\.html$")


@dataclass(frozen=True)
class TargetValidationResult:
    valid: bool
    code: str
    message: str
    report: dict[str, object]


def target_url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def diagnose_dns(hostname: str) -> dict[str, object]:
    """Read-only DNS diagnostics. Never connect to blocked/private addresses."""
    report: dict[str, object] = {
        "hostname": hostname,
        "runtime": "docker-or-linux",
        "httpx_trust_env": False,
        "proxy_environment_present": any(
            os.environ.get(key)
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            )
        ),
    }
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as handle:
            report["dns_nameservers"] = [
                line.split()[1] for line in handle if line.strip().startswith("nameserver ") and len(line.split()) >= 2
            ]
    except OSError:
        report["dns_nameservers"] = []
    try:
        addresses = sorted({str(item[4][0]) for item in socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)})
    except OSError:
        report.update({"dns_status": "DNS_ERROR", "resolved_addresses": []})
        return report
    report["resolved_addresses"] = addresses
    blocked = [value for value in addresses if not ipaddress.ip_address(value).is_global]
    report["blocked_addresses"] = blocked
    report["dns_status"] = "SSRF_BLOCKED" if blocked else ("PUBLIC" if addresses else "DNS_ERROR")
    report["recommendation"] = (
        "检查 Windows/WSL2/Docker DNS 分流及经批准的企业代理。禁止直接放行私网 IP"
        if blocked
        else "DNS 检查通过。仍需检查真实请求路径、代理与重定向"
    )
    return report


def _public_addresses(hostname: str) -> list[str]:
    diagnosis = diagnose_dns(hostname)
    if diagnosis["dns_status"] == "DNS_ERROR":
        raise CollectorError("采集入口 DNS 解析失败", code="DNS_ERROR", retryable=True)
    raw_addresses = diagnosis.get("resolved_addresses")
    raw_blocked = diagnosis.get("blocked_addresses")
    addresses = [str(value) for value in raw_addresses] if isinstance(raw_addresses, list) else []
    blocked = [str(value) for value in raw_blocked] if isinstance(raw_blocked, list) else []
    if blocked:
        allowed_hosts = {host.lower().rstrip(".") for host in settings.SSRF_ALLOWED_HOSTS}
        pinned_ips = set(settings.SSRF_ALLOWED_PRIVATE_IPS)
        # An exact host match is necessary but insufficient: private endpoints
        # must be explicitly pinned to prevent arbitrary internal access.
        if hostname.lower().rstrip(".") not in allowed_hosts or not pinned_ips or not set(blocked).issubset(pinned_ips):
            raise CollectorError("采集入口解析到未授权的非公网地址; 已拒绝访问", code="SSRF_BLOCKED")
    return addresses


def _identity_matches(target: SourceTarget, identity: str) -> bool:
    actual = normalize_match_text(identity).replace("#", "")
    aliases = [target.product.name, *(alias.alias for alias in target.product.aliases.all())]
    expected = {normalize_match_text(alias).replace("#", "") for alias in aliases if alias.strip()}
    if not expected:
        return False
    # Identity comes from the topic header, so require exact containment in either
    # direction instead of the broad post-content substring matcher.
    return any(actual == value or actual.startswith(value + "官方") for value in expected)


def _persist(target: SourceTarget, result: TargetValidationResult) -> TargetValidationResult:
    target.validation_status = TargetValidationStatus.VALID if result.valid else TargetValidationStatus.INVALID
    target.validated_at = timezone.now()
    target.validated_url_hash = target_url_hash(target.target_url) if result.valid else ""
    target.validation_error_code = "" if result.valid else result.code
    target.validation_error_message = "" if result.valid else result.message
    target.validation_report = result.report
    target.save(
        update_fields=(
            "validation_status",
            "validated_at",
            "validated_url_hash",
            "validation_error_code",
            "validation_error_message",
            "validation_report",
            "updated_at",
        )
    )
    return result


def validate_source_target(target: SourceTarget) -> TargetValidationResult:
    report: dict[str, object] = {"url": target.target_url, "source": target.source.code}
    if target.source.code == "HONOR_CLUB":
        report["network_diagnostics"] = diagnose_dns("club.honor.com")
    try:
        if target.source.code != "HONOR_CLUB":
            raise CollectorError("当前仅支持验证荣耀俱乐部入口", code="UNSUPPORTED_SOURCE")
        valid, error = validate_honor_url(target.target_url)
        if not valid:
            raise CollectorError(error, code="INVALID_URL")
        parsed = urlparse(target.target_url)
        match = _TOPIC_ID.search(parsed.path)
        if not match:
            raise CollectorError("采集入口必须是荣耀俱乐部话题列表页", code="INVALID_TOPIC_URL")
        report["resolved_addresses"] = _public_addresses(parsed.hostname or "")
        response = HonorClubClient(timeout_seconds=12).get_html(target.target_url, request_interval_seconds=3)
        report.update({"http_status": response.status_code, "elapsed_ms": response.elapsed_ms})
        if not is_valid_topic_page(response.text):
            raise CollectorError("页面不是有效的荣耀俱乐部话题列表", code="INVALID_TOPIC_PAGE")
        identity = extract_topic_identity(response.text)
        report["topic_identity"] = identity
        if not _identity_matches(target, identity):
            raise CollectorError(
                f"入口话题“{identity or '未知'}”与手机“{target.product.name}”不匹配",
                code="PRODUCT_MISMATCH",
            )
        topic_id = int(match.group("topic_id"))
        records = parse_topic_page(response.text, topic_id=topic_id)
        if not records:
            raise CollectorError("入口页面未解析到有效帖子", code="NO_THREADS")
        report.update(
            {
                "topic_id": topic_id,
                "parsed_thread_count": len(records),
                "sample_thread_ids": [str(record.payload.get("thread_id", "")) for record in records[:3]],
            }
        )
        return _persist(target, TargetValidationResult(True, "", "入口验证通过", report))
    except CollectorError as exc:
        report["error_code"] = exc.code
        return _persist(target, TargetValidationResult(False, exc.code, str(exc), report))
