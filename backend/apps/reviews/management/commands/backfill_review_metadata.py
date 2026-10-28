"""仅使用已持久化的可靠原始证据补全发布时间和公开地域。"""

from __future__ import annotations

import re
from typing import Any

from collectors.honor_club.date_parser import parse_honor_datetime
from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction

from apps.reviews.models import ReviewRecord

_FULL_DATE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}")
_PUBLIC_REGION = re.compile(r"^[\u4e00-\u9fff]{2,12}$")


class Command(BaseCommand):
    help = "从已有 raw_data 的可靠证据安全补全反馈发布时间和公开来源地域; 默认仅预览"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--apply", action="store_true", help="实际写入; 未提供时仅 dry-run")
        parser.add_argument("--dry-run", action="store_true", help="显式仅预览(兼容运维脚本)")
        parser.add_argument("--source-target", type=int, help="仅扫描指定采集入口")

    def handle(self, *args: object, **options: Any) -> None:
        del args
        apply_changes = bool(options["apply"] and not options["dry_run"])
        queryset = ReviewRecord.objects.order_by("id")
        if options.get("source_target"):
            queryset = queryset.filter(source_target_id=options["source_target"])
        counters = {"scanned": 0, "published": 0, "region": 0, "unresolved": 0, "errors": 0}
        with transaction.atomic():
            for review in queryset.iterator(chunk_size=500):
                counters["scanned"] += 1
                changed: list[str] = []
                try:
                    raw = review.raw_data if isinstance(review.raw_data, dict) else {}
                    raw_time = str(raw.get("published_at_raw", "")).strip()
                    if review.published_at is None and _FULL_DATE.search(raw_time):
                        parsed = parse_honor_datetime(raw_time)
                        if parsed is not None:
                            review.published_at = parsed
                            changed.append("published_at")
                            counters["published"] += 1
                    region = str(raw.get("public_region", "")).strip()
                    if not review.source_region and _PUBLIC_REGION.fullmatch(region):
                        review.source_region = region
                        review.region_evidence = "public_ip_region"
                        changed.extend(("source_region", "region_evidence"))
                        counters["region"] += 1
                    if not changed:
                        counters["unresolved"] += 1
                    elif apply_changes:
                        review.save(update_fields=(*changed, "updated_at"))
                except Exception:
                    counters["errors"] += 1
            if not apply_changes:
                transaction.set_rollback(True)
        mode = "正式写入" if apply_changes else "仅预览"
        self.stdout.write(
            f"{mode}: 扫描 {counters['scanned']}; 补全发布时间 {counters['published']}; "
            f"补全地域 {counters['region']}; 无法补全 {counters['unresolved']}; 错误 {counters['errors']}"
        )
