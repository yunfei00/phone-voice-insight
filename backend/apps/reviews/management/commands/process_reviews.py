"""Run deterministic review governance without external network access."""

# ruff: noqa: RUF001

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import Q, QuerySet

from apps.reviews.models import ReviewRecord
from apps.reviews.services.governance_pipeline import process_reviews


class Command(BaseCommand):
    help = "处理 ReviewRecord 数据质量并生成 AI 语料，不访问外网"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--product", help="产品 ID、normalized_name 或名称")
        parser.add_argument("--source", help="来源 ID 或 code")
        parser.add_argument("--limit", type=int, help="最多处理记录数")
        parser.add_argument("--reprocess", action="store_true", help="重跑当前处理器版本")
        parser.add_argument("--dry-run", action="store_true", help="只计算统计，不写入治理结果")
        parser.add_argument("--batch-size", type=int, default=100, help="数据库迭代批大小，默认 100")

    def _queryset(self, options: dict[str, Any]) -> QuerySet[ReviewRecord]:
        queryset = ReviewRecord.objects.all()
        product = options.get("product")
        if product:
            product_value = str(product)
            product_filter = Q(product__normalized_name__iexact=product_value) | Q(product__name__iexact=product_value)
            if product_value.isdigit():
                product_filter |= Q(product_id=int(product_value))
            queryset = queryset.filter(product_filter)
        source = options.get("source")
        if source:
            source_value = str(source)
            source_filter = Q(source__code__iexact=source_value)
            if source_value.isdigit():
                source_filter |= Q(source_id=int(source_value))
            queryset = queryset.filter(source_filter)
        limit = options.get("limit")
        if limit is not None:
            if limit < 1 or limit > 10_000:
                raise CommandError("--limit 必须在 1 到 10000 之间")
            review_ids = queryset.order_by("id").values_list("id", flat=True)[:limit]
            queryset = queryset.filter(id__in=review_ids)
        return queryset

    def handle(self, *args: object, **options: Any) -> None:
        del args
        batch_size = int(options["batch_size"])
        if batch_size < 1 or batch_size > 1000:
            raise CommandError("--batch-size 必须在 1 到 1000 之间")
        result = process_reviews(
            self._queryset(options),
            batch_size=batch_size,
            persist=not bool(options["dry_run"]),
            reprocess=bool(options["reprocess"]),
        )
        output = result.as_dict()
        output["dry_run"] = bool(options["dry_run"])
        self.stdout.write(json.dumps(output, ensure_ascii=False, sort_keys=True))
