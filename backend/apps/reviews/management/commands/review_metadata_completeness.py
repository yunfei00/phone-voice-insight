"""输出发布时间与地域字段完整率。"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.reviews.models import ReviewRecord
from apps.reviews.services.metadata_completeness import metadata_completeness


class Command(BaseCommand):
    help = "统计反馈发布时间、IP属地、用户资料地区的非空数量、非空率和失败原因"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--product", help="产品 normalized_name")
        parser.add_argument("--source-target", type=int, help="采集入口 ID")

    def handle(self, *args: object, **options: Any) -> None:
        del args
        queryset = ReviewRecord.objects.select_related("product")
        if options.get("product"):
            queryset = queryset.filter(product__normalized_name=str(options["product"]))
        if options.get("source_target"):
            queryset = queryset.filter(source_target_id=int(options["source_target"]))
        self.stdout.write(json.dumps(metadata_completeness(queryset), ensure_ascii=False, indent=2, default=str))
