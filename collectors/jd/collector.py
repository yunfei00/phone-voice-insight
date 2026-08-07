"""京东公开可见评价 PoC 采集器。"""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import urlparse

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
from collectors.jd.client import JDClient, validate_https_url
from collectors.jd.constants import (
    MAX_PAGE_SIZE,
    MAX_PAGES,
    MIN_REQUEST_INTERVAL_SECONDS,
    PRODUCT_HOST,
    VERIFIED_COMMENT_FIELD_MAP,
)
from collectors.jd.jsonp import parse_json_or_jsonp
from collectors.jd.normalizer import normalize_jd_record
from collectors.jd.parser import parse_comments_payload, parse_product_page, validate_product_identity


class JDCollector(BaseCollector):
    def __init__(self, *, client: JDClient | None = None) -> None:
        self.client = client or JDClient()

    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        errors: list[str] = []
        try:
            validate_https_url(target.target_url, allowed_hosts=frozenset({PRODUCT_HOST}))
        except CollectorError as exc:
            errors.append(str(exc))
        product_id = str(target.config.get("product_id", ""))
        parsed = urlparse(target.target_url)
        expected_path = f"/{product_id}.html"
        if not product_id.isdigit():
            errors.append("product_id 必须为纯数字")
        if parsed.path != expected_path or parsed.query or parsed.fragment:
            errors.append("商品 URL 必须与 product_id 精确对应且不得包含 query/fragment")
        if target.external_id != f"jd:{product_id}":
            errors.append("external_id 必须为 jd:{product_id}")
        try:
            interval = float(target.config.get("request_interval_seconds", 0))
        except (TypeError, ValueError):
            interval = 0
        if interval < MIN_REQUEST_INTERVAL_SECONDS:
            errors.append("request_interval_seconds 不得小于 4")
        for name, maximum in (("max_pages", MAX_PAGES), ("page_size", MAX_PAGE_SIZE)):
            try:
                value = int(target.config.get(name, 0))
            except (TypeError, ValueError):
                value = 0
            if not 1 <= value <= maximum:
                errors.append(f"{name} 必须在 1..{maximum} 范围内")
        return ValidationResult(is_valid=not errors, errors=tuple(errors))

    def fetch_page(self, request: CollectionRequest) -> RawPage:
        validation = self.validate_target(request.target)
        if not validation.is_valid:
            raise CollectorError("; ".join(validation.errors), code="INVALID_TARGET")
        page_kind = str(request.checkpoint.metadata.get("page_kind", "product"))
        interval = float(request.target.config["request_interval_seconds"])
        if page_kind == "product":
            response = self.client.get_product_page(
                product_url=request.target.target_url,
                request_interval_seconds=interval,
            )
        elif page_kind == "comments":
            page = request.checkpoint.page
            page_size = int(request.checkpoint.metadata.get("page_size", MAX_PAGE_SIZE))
            if not 1 <= page <= MAX_PAGES or not 1 <= page_size <= MAX_PAGE_SIZE:
                raise CollectorError("京东 PoC 分页超过强制上限", code="LIMIT_EXCEEDED")
            response = self.client.get_comments_page(
                product_url=request.target.target_url,
                request_interval_seconds=interval,
            )
        else:
            raise CollectorError("未知京东页面类型", code="INVALID_REQUEST")
        return RawPage(
            content=response.text,
            fetched_at=datetime.now(UTC),
            checkpoint=request.checkpoint,
            metadata={
                **request.checkpoint.metadata,
                "page_kind": page_kind,
                "request_url": response.url,
                "http_status": response.status_code,
                "content_type": response.content_type,
                "elapsed_ms": response.elapsed_ms,
            },
        )

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        content = (
            raw_page.content.decode("utf-8", errors="strict")
            if isinstance(raw_page.content, bytes)
            else raw_page.content
        )
        page_kind = str(raw_page.metadata.get("page_kind", "product"))
        if page_kind == "product":
            product_id = str(raw_page.metadata.get("product_id", ""))
            record = parse_product_page(content, product_id=product_id)
            validate_product_identity(record, product_id=product_id)
            return [record]
        if page_kind == "comments":
            field_map = raw_page.metadata.get("field_map", VERIFIED_COMMENT_FIELD_MAP)
            if not isinstance(field_map, dict) or not field_map:
                raise CollectorError("当前评论字段结构尚未现场验证", code="RESPONSE_SCHEMA_NOT_VERIFIED")
            payload = parse_json_or_jsonp(content, expected_callback=raw_page.metadata.get("callback"))
            return parse_comments_payload(payload, field_map=field_map)
        raise CollectorError("未知京东页面类型", code="PARSE_CONTEXT")

    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        if raw_record.record_type not in {"REVIEW", "APPEND_REVIEW"}:
            raise CollectorError("商品元数据不能持久化为评价", code="INVALID_RECORD")
        return normalize_jd_record(raw_record)
