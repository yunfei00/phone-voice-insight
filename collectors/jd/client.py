"""京东 PoC 单并发、固定身份、失败关闭 HTTP 客户端。"""

from __future__ import annotations

import ipaddress
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from collectors.base import CollectorError
from collectors.jd.constants import (
    BLOCK_MARKERS,
    BLOCK_STATUS_CODES,
    FIXED_USER_AGENT,
    MIN_REQUEST_INTERVAL_SECONDS,
    PRODUCT_HOST,
    REQUEST_TIMEOUT_SECONDS,
    VERIFIED_COMMENT_ENDPOINT,
    VERIFIED_COMMENT_HOSTS,
)


@dataclass(frozen=True)
class JDHTTPResponse:
    text: str
    url: str
    status_code: int
    content_type: str
    elapsed_ms: int


def validate_https_url(url: str, *, allowed_hosts: frozenset[str]) -> None:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme != "https" or not hostname or parsed.username or parsed.password:
        raise CollectorError("仅允许无 userinfo 的 HTTPS URL", code="INVALID_TARGET")
    if parsed.port not in (None, 443):
        raise CollectorError("不允许自定义端口", code="INVALID_TARGET")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise CollectorError("不允许 IP 地址目标", code="INVALID_TARGET")
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname not in allowed_hosts:
        raise CollectorError("目标 host 不在京东公开页面白名单", code="INVALID_TARGET")


class JDClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper
        self._last_request_at: float | None = None

    def _wait(self, interval: float) -> None:
        safe_interval = max(interval, MIN_REQUEST_INTERVAL_SECONDS)
        if self._last_request_at is not None:
            remaining = safe_interval - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleeper(remaining)

    def _get(self, url: str, *, referer: str, allowed_hosts: frozenset[str], interval: float) -> JDHTTPResponse:
        validate_https_url(url, allowed_hosts=allowed_hosts)
        self._wait(interval)
        started_at = self._clock()
        headers = {"User-Agent": FIXED_USER_AGENT, "Referer": referer, "Accept": "text/html,application/json"}
        try:
            with httpx.Client(
                headers=headers,
                timeout=REQUEST_TIMEOUT_SECONDS,
                follow_redirects=False,
                transport=self._transport,
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise CollectorError("京东公开页面请求失败", code="HTTP_ERROR", retryable=False) from exc
        finally:
            self._last_request_at = self._clock()
        elapsed_ms = round((self._clock() - started_at) * 1000)
        if response.is_redirect:
            location = response.headers.get("location", "")
            raise CollectorError(f"京东返回异常跳转: {location}", code="UNEXPECTED_REDIRECT")
        if response.status_code in BLOCK_STATUS_CODES:
            raise CollectorError(f"京东返回访问限制状态 {response.status_code}", code="ACCESS_BLOCKED")
        if response.status_code >= 500:
            raise CollectorError(f"京东返回服务错误 {response.status_code}", code="UPSTREAM_ERROR", retryable=False)
        if response.status_code != 200:
            raise CollectorError(f"京东返回非预期状态 {response.status_code}", code="HTTP_STATUS_ERROR")
        lowered = response.text.casefold()
        if any(marker.casefold() in lowered for marker in BLOCK_MARKERS):
            raise CollectorError("京东响应包含登录或访问验证页面", code="ACCESS_BLOCKED")
        return JDHTTPResponse(
            text=response.text,
            url=str(response.url),
            status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            elapsed_ms=elapsed_ms,
        )

    def get_product_page(self, *, product_url: str, request_interval_seconds: float) -> JDHTTPResponse:
        return self._get(
            product_url,
            referer=product_url,
            allowed_hosts=frozenset({PRODUCT_HOST}),
            interval=request_interval_seconds,
        )

    def get_comments_page(
        self,
        *,
        product_url: str,
        request_interval_seconds: float,
    ) -> JDHTTPResponse:
        if VERIFIED_COMMENT_ENDPOINT is None or not VERIFIED_COMMENT_HOSTS:
            raise CollectorError("当前评论接口尚未通过真实页面验证", code="ENDPOINT_NOT_VERIFIED")
        return self._get(
            VERIFIED_COMMENT_ENDPOINT,
            referer=product_url,
            allowed_hosts=VERIFIED_COMMENT_HOSTS,
            interval=request_interval_seconds,
        )
