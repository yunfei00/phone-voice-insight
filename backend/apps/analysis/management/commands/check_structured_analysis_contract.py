import json
from pathlib import Path
from typing import Any

from ai.taxonomy import load_taxonomy
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "校验结构化分析 V1 的标签、JSON Schema 和 Prompt 版本资产"

    def handle(self, *args: Any, **options: Any) -> None:
        del args, options
        root = Path(__file__).resolve().parents[5]
        taxonomy = load_taxonomy()
        schema = json.loads((root / "schemas" / "structured_analysis_v1.schema.json").read_text(encoding="utf-8"))
        prompt = (root / "prompts" / "structured_analysis_v1.md").read_text(encoding="utf-8")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise CommandError("JSON_SCHEMA_DRAFT_INVALID")
        if schema.get("properties", {}).get("taxonomy_version", {}).get("const") != taxonomy.taxonomy_version:
            raise CommandError("TAXONOMY_SCHEMA_VERSION_MISMATCH")
        if "不可信输入" not in prompt or "只输出 JSON" not in prompt:
            raise CommandError("PROMPT_SAFETY_RULES_MISSING")
        self.stdout.write(self.style.SUCCESS("Structured analysis contract 1.0.0 is valid"))
