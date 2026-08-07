"""受限执行京东公开可见评价 PoC。"""

import json
from dataclasses import asdict
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.collection.models import CollectionTask
from apps.collection.services.collection_runner import preview_target, run_collection
from apps.sources.models import SourceTarget


class Command(BaseCommand):
    help = "低频采集荣耀 Power2 京东公开可见评价, 强制最多 3 页/30 条主评价"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--target-id", type=int, required=True)
        parser.add_argument("--pages", type=int, default=1)
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *_args: Any, **options: Any) -> None:
        pages = int(options["pages"])
        limit = int(options["limit"])
        if not 1 <= pages <= 3:
            raise CommandError("PoC --pages 必须在 1 到 3 之间")
        if not 1 <= limit <= 30:
            raise CommandError("PoC --limit 必须在 1 到 30 之间")
        try:
            target = SourceTarget.objects.select_related("source", "product").get(
                pk=options["target_id"],
                source__code="JD",
                is_active=True,
            )
        except SourceTarget.DoesNotExist as exc:
            raise CommandError("未找到启用且已完成现场验证的京东采集入口") from exc

        if options["dry_run"]:
            summary = preview_target(target, limit=limit, pages=pages)
        else:
            task = CollectionTask.objects.create(source_target=target, requested_limit=limit)
            summary = run_collection(task.id, limit_override=limit, pages_override=pages)

        self.stdout.write(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))
