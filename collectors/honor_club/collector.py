"""荣耀俱乐部公开 HTML 采集器。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from collectors.base import (
    BaseCollector,
    CollectionRequest,
    CollectorError,
    CollectorTarget,
    NormalizedReview,
    RawPage,
    RawRecord,
    ValidationResult,
)
from collectors.honor_club.client import HonorClubClient, validate_honor_url
from collectors.honor_club.normalizer import normalize_honor_record
from collectors.honor_club.parser import parse_thread_page, parse_topic_page

_TOPIC_ID_PATTERN = re.compile(r"threadtopic-(\d+)-\d+\.html")


def _positive_int(value: Any, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, 1), maximum)


class HonorClubCollector(BaseCollector):
    def __init__(self, client: HonorClubClient | None = None) -> None:
        self.client = client or HonorClubClient()

    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        if target.source_code != "HONOR_CLUB":
            errors.append("采集器只接受 HONOR_CLUB 来源")
        is_valid_url, url_error = validate_honor_url(target.target_url)
        if not is_valid_url:
            errors.append(url_error)
        if "/threadtopic-" in target.target_url:
            topic_id = target.config.get("topic_id")
            match = _TOPIC_ID_PATTERN.search(target.target_url)
            if not match:
                errors.append("话题页缺少有效 topic id")
            elif topic_id is not None and str(topic_id) != match.group(1):
                errors.append("配置 topic_id 与 URL 不一致")
        if float(target.config.get("request_interval_seconds", 3)) < 3:
            warnings.append("请求间隔已强制提升到 3 秒")
        return ValidationResult(is_valid=not errors, errors=tuple(errors), warnings=tuple(warnings))

    def fetch_page(self, request: CollectionRequest) -> RawPage:
        validation = self.validate_target(request.target)
        if not validation.is_valid:
            raise CollectorError("; ".join(validation.errors), code="INVALID_TARGET")

        page_kind = str(request.checkpoint.metadata.get("page_kind", "topic"))
        if page_kind == "topic":
            match = _TOPIC_ID_PATTERN.search(request.target.target_url)
            if not match:
                raise CollectorError("无法从目标 URL 解析 topic id", code="INVALID_TARGET")
            topic_id = _positive_int(request.target.config.get("topic_id", match.group(1)), default=595, maximum=999999)
            url = f"https://club.honor.com/cn/threadtopic-{topic_id}-{request.checkpoint.page}.html"
        elif page_kind == "thread":
            url = request.target.target_url
        else:
            raise CollectorError("未知页面类型", code="INVALID_REQUEST")

        interval = max(float(request.target.config.get("request_interval_seconds", 3)), 3.0)
        response = self.client.get_html(url, request_interval_seconds=interval)
        return RawPage(
            content=response.text,
            fetched_at=datetime.now(UTC),
            checkpoint=request.checkpoint,
            metadata={
                **request.checkpoint.metadata,
                "page_kind": page_kind,
                "request_url": response.url,
                "http_status": response.status_code,
                "elapsed_ms": response.elapsed_ms,
            },
        )

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        if isinstance(raw_page.content, bytes):
            html = raw_page.content.decode("utf-8", errors="replace")
        else:
            html = raw_page.content
        page_kind = str(raw_page.metadata.get("page_kind", "topic"))
        if page_kind == "topic":
            topic_id = _positive_int(raw_page.metadata.get("topic_id", 595), default=595, maximum=999999)
            return parse_topic_page(html, topic_id=topic_id)
        if page_kind == "thread":
            thread_id = str(raw_page.metadata.get("thread_id", ""))
            thread_url = str(raw_page.metadata.get("request_url", ""))
            listing_data = raw_page.metadata.get("listing_data", {})
            if not thread_id or not isinstance(listing_data, dict):
                raise CollectorError("帖子页缺少解析上下文", code="PARSE_CONTEXT")
            return parse_thread_page(
                html,
                thread_id=thread_id,
                thread_url=thread_url,
                listing_data=listing_data,
            )
        raise CollectorError("未知页面类型", code="PARSE_CONTEXT")

    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        if raw_record.record_type == "THREAD_LINK":
            raise CollectorError("话题列表记录不能直接持久化", code="INVALID_RECORD")
        return normalize_honor_record(raw_record)
