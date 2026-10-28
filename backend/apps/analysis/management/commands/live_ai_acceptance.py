"""Explicit, bounded live AI acceptance command; disabled by default."""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.test.utils import override_settings

from apps.products.models import Product
from apps.reviews.services.automatic_pipeline import run_automatic_pipeline


class Command(BaseCommand):
    help = "最多对 10 条真实数据执行一次显式 AI 自动流水线验收"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--product-id", type=int, required=True)
        parser.add_argument("--source-id", type=int)
        parser.add_argument("--max-items", type=int, default=10)

    def handle(self, *args: object, **options: Any) -> None:
        del args
        if not settings.AI_LIVE_ACCEPTANCE_ENABLED:
            raise CommandError("真实 AI 验收未启用; 请显式设置 AI_LIVE_ACCEPTANCE_ENABLED=true")
        maximum = min(int(settings.AI_LIVE_ACCEPTANCE_MAX_ITEMS), 10)
        max_items = int(options["max_items"])
        if max_items < 1 or max_items > maximum:
            raise CommandError(f"--max-items 必须在 1 到 {maximum} 之间")
        if not Product.objects.filter(pk=options["product_id"]).exists():
            raise CommandError("产品不存在")
        with override_settings(AI_AUTOMATION_ENABLED=True, AI_AUTOMATION_BATCH_SIZE=max_items):
            result = run_automatic_pipeline(options["product_id"], options.get("source_id"))
        self.stdout.write(json.dumps(result.as_dict(), ensure_ascii=False, default=str, indent=2))
