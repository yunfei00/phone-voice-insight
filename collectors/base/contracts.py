"""采集器和后端任务之间的最小稳定契约。"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CollectorTarget:
    source_code: str
    product_code: str
    target_url: str
    external_id: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionCheckpoint:
    cursor: str = ""
    page: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CollectionRequest:
    target: CollectorTarget
    checkpoint: CollectionCheckpoint = field(default_factory=CollectionCheckpoint)
    limit: int | None = None


@dataclass(frozen=True)
class RawPage:
    content: str | bytes
    fetched_at: datetime
    checkpoint: CollectionCheckpoint
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawRecord:
    external_id: str | None
    record_type: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class NormalizedReview:
    external_id: str | None
    parent_external_id: str | None
    record_type: str
    title: str = ""
    content: str = ""
    published_at: datetime | None = None
    author_role: str = "UNKNOWN"
    is_official: bool = False
    is_append_review: bool = False
    software_version: str = ""
    source_url: str = ""
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    is_valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class CollectorError(RuntimeError):
    def __init__(self, message: str, *, code: str = "COLLECTOR_ERROR", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class BaseCollector(ABC):
    @abstractmethod
    def validate_target(self, target: CollectorTarget) -> ValidationResult:
        """验证入口配置，但不得发起越权访问。"""

    @abstractmethod
    def fetch_page(self, request: CollectionRequest) -> RawPage:
        """按限速与平台许可抓取一页公开内容。"""

    @abstractmethod
    def parse_records(self, raw_page: RawPage) -> list[RawRecord]:
        """从一页原始响应提取记录。"""

    @abstractmethod
    def normalize_record(self, raw_record: RawRecord) -> NormalizedReview:
        """将来源记录转换为统一反馈契约。"""
