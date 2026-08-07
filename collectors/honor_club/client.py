"""单并发、低频、无 Cookie 持久化的荣耀俱乐部公开 HTML 客户端。"""

from __future__ import annotations

import ipaddress
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from collectors.base import CollectorError

HONOR_HOST = "club.honor.com"
DEFAULT_USER_AGENT = "PhoneVoiceInsightPoC/0.2 (public-page low-frequency collector)"
_ALLOWED_PATH_PATTERN = re.compile(r"^/cn/(?:threadtopic-\d+-\d+|thread-\d+-\d+-\d+)\.html$")
_CHALLENGE_MARKERS = (
    "请输入验证码",
    "安全验证",
    "访问过于频繁",
    "请求过于频繁",
    "captcha",
)


@dataclass(frozen=True)
class HonorHttpResponse:
    text: str
    url: str
    status_code: int
    elapsed_ms: int


def validate_honor_url(url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "目标 URL 无法解析"

    try:
        hostname = (parsed.hostname or "").lower()
        has_custom_port = parsed.port is not None
    except ValueError:
        return False, "目标 URL 的主机或端口无效"

    if parsed.scheme != "https":
        return False, "只允许 https URL"
    if parsed.username or parsed.password or has_custom_port:
        return False, "目标 URL 不允许认证信息或自定义端口"
    if hostname != HONOR_HOST:
        return False, "只允许 club.honor.com 域名"
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return False, "不允许 IP 地址目标"
    if not _ALLOWED_PATH_PATTERN.fullmatch(parsed.path):
        return False, "只允许荣耀话题页或帖子详情页"
    if parsed.query or parsed.fragment:
        return False, "目标 URL 不允许查询参数或片段"
    return True, ""


class HonorClubClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 15.0,
        user_agent: str = DEFAULT_USER_AGENT,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self._sleeper = sleeper
        self._clock = clock
        self._last_request_started: float | None = None

    def get_html(self, url: str, *, request_interval_seconds: float) -> HonorHttpResponse:
        is_valid, error = validate_honor_url(url)
        if not is_valid:
            raise CollectorError(error, code="INVALID_TARGET")

        interval = max(3.0, request_interval_seconds)
        if self._last_request_started is not None:
            remaining = interval - (self._clock() - self._last_request_started)
            if remaining > 0:
                self._sleeper(remaining)

        started = self._clock()
        self._last_request_started = started
        try:
            # 每次请求使用独立 client, 响应 Cookie 不会进入下一次请求。
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9",
                },
            ) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            raise CollectorError("荣耀俱乐部网络请求失败", code="HTTP_ERROR", retryable=True) from exc

        elapsed_ms = int((self._clock() - started) * 1000)
        if response.status_code in {403, 429}:
            raise CollectorError(
                f"荣耀俱乐部拒绝公开页面请求 (HTTP {response.status_code})",
                code=f"HTTP_{response.status_code}",
            )
        if response.status_code >= 500:
            raise CollectorError(
                f"荣耀俱乐部服务异常 (HTTP {response.status_code})",
                code="HTTP_5XX",
                retryable=True,
            )
        if response.status_code != 200:
            raise CollectorError(
                f"荣耀俱乐部返回非预期状态 (HTTP {response.status_code})",
                code="HTTP_STATUS",
            )

        final_url = str(response.url)
        final_valid, _ = validate_honor_url(final_url)
        if not final_valid:
            raise CollectorError("荣耀俱乐部发生异常跳转, 已停止采集", code="UNEXPECTED_REDIRECT")

        content_type = response.headers.get("content-type", "").lower()
        if "html" not in content_type:
            raise CollectorError("荣耀俱乐部未返回 HTML", code="INVALID_CONTENT_TYPE")

        lower_text = response.text.casefold()
        if any(marker.casefold() in lower_text for marker in _CHALLENGE_MARKERS):
            raise CollectorError("荣耀俱乐部出现验证码或访问限制页面", code="CHALLENGE_PAGE")
        if "<title>登录" in response.text and "threadlist" not in response.text:
            raise CollectorError("荣耀俱乐部出现登录墙", code="LOGIN_WALL")

        return HonorHttpResponse(
            text=response.text,
            url=final_url,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
        )
