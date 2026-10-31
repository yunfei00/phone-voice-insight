from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from apps.assistant.models import RagIndexRun, RagIndexRunStatus
from apps.assistant.tasks import run_rag_backfill
from apps.reviews.models import RecordType, ReviewRecord


class Command(BaseCommand):
    help = "创建或继续 RAG 历史帖子索引, 支持分批断点续跑。"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--run-id", type=int)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--enqueue", action="store_true", help="提交 Celery 后台执行")

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        run_id = options.get("run_id")
        if run_id:
            run = RagIndexRun.objects.get(pk=run_id)
            if run.status in {RagIndexRunStatus.SUCCESS, RagIndexRunStatus.PARTIAL}:
                self.stdout.write(self.style.WARNING("指定索引任务已经结束。"))
                return
        else:
            run = RagIndexRun.objects.create(
                requested_count=ReviewRecord.objects.filter(record_type=RecordType.THREAD).count()
            )
        batch_size = min(max(int(options["batch_size"]), 1), 500)
        if options["enqueue"]:
            run_rag_backfill.delay(run.id, batch_size)
            self.stdout.write(self.style.SUCCESS(f"已提交索引任务 #{run.id}"))
            return
        result = run_rag_backfill(run.id, batch_size)
        self.stdout.write(self.style.SUCCESS(f"索引任务 #{run.id}: {result}"))
