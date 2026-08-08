"""受限执行荣耀俱乐部 PoC。"""

import json
from dataclasses import asdict
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from apps.collection.models import CollectionTask, CollectionTaskType
from apps.collection.services.collection_runner import preview_target, run_collection
from apps.sources.models import SourceTarget


class Command(BaseCommand):
    help = "低频采集荣耀 Power2 公开话题; 正式运行最多 200 个帖子"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--target-id", type=int, required=True)
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--task-type",
            choices=(CollectionTaskType.FULL, CollectionTaskType.INCREMENTAL),
            default=CollectionTaskType.INCREMENTAL,
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        limit = int(options["limit"])
        maximum = 10 if options["dry_run"] else 200
        if limit < 1 or limit > maximum:
            raise CommandError(f"--limit 必须在 1 到 {maximum} 之间")
        try:
            target = SourceTarget.objects.select_related("source", "product").get(
                pk=options["target_id"],
                source__code="HONOR_CLUB",
                is_active=True,
            )
        except SourceTarget.DoesNotExist as exc:
            raise CommandError("未找到启用的荣耀俱乐部采集入口") from exc

        if options["dry_run"]:
            summary = preview_target(target, limit=limit)
        else:
            task = CollectionTask.objects.create(
                source_target=target,
                task_type=options["task_type"],
                requested_limit=limit,
            )
            summary = run_collection(task.id, limit_override=limit)

        self.stdout.write(json.dumps(asdict(summary), ensure_ascii=False, indent=2, default=str))
