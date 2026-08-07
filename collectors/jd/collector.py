from typing import Never

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


class JDCollector(BaseCollector):
    """京东采集器骨架；Phase 1 明确不访问真实网站。"""

    def _not_implemented(self) -> Never:
        raise CollectorError("JD collector not implemented", code="NOT_IMPLEMENTED")

    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        del target
        self._not_implemented()

    def fetch_page(self, request: CollectionRequest) -> RawPage:
        del request
        self._not_implemented()

    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        del raw_page
        self._not_implemented()

    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        del raw_record
        self._not_implemented()
