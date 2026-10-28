"""幂等初始化荣耀 Power 系列及其已验证公开话题入口。"""

from __future__ import annotations

import re
import unicodedata

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.collection.models import CollectionTargetState
from apps.products.models import Brand, Product, ProductAlias
from apps.sources.models import DataSource, SourceTarget, SourceType, TargetType


def _identity(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value)).casefold()


PRODUCTS = (
    {
        "name": "荣耀 Power2",
        "normalized_name": "HONOR_POWER2",
        "series": "Power",
        "aliases": ("荣耀Power2", "荣耀 Power 2", "HONOR Power2", "Power2"),
        "target_name": "荣耀Power2官方话题",
        "target_url": "https://club.honor.com/cn/threadtopic-595-1.html",
        "topic_id": "595",
    },
    {
        "name": "荣耀 Power",
        "normalized_name": "HONOR_POWER",
        "series": "Power",
        "aliases": ("荣耀Power", "HONOR Power", "Power"),
        "target_name": "荣耀Power官方话题",
        "target_url": "https://club.honor.com/cn/threadtopic-521-1.html",
        "topic_id": "521",
    },
)


class Command(BaseCommand):
    help = "幂等创建荣耀 Power/Power2 手机及荣耀俱乐部公开话题入口"

    @transaction.atomic
    def handle(self, *args: object, **options: object) -> None:
        del args, options
        brand, _ = Brand.objects.update_or_create(code="HONOR", defaults={"name": "荣耀", "is_active": True})
        source, _ = DataSource.objects.update_or_create(
            code="HONOR_CLUB",
            defaults={"name": "荣耀俱乐部", "source_type": SourceType.COMMUNITY, "is_active": True},
        )
        for definition in PRODUCTS:
            matches = [
                product
                for product in Product.objects.filter(brand=brand)
                if _identity(product.name) == _identity(str(definition["name"]))
                or product.normalized_name == definition["normalized_name"]
            ]
            if len(matches) > 1:
                raise CommandError(f"发现重复产品“{definition['name']}”; 请先人工确认后再初始化")
            if matches:
                product = matches[0]
                product.name = str(definition["name"])
                product.normalized_name = str(definition["normalized_name"])
                product.series = str(definition["series"])
                product.is_active = True
                product.save(update_fields=("name", "normalized_name", "series", "is_active", "updated_at"))
            else:
                product = Product.objects.create(
                    brand=brand,
                    name=str(definition["name"]),
                    normalized_name=str(definition["normalized_name"]),
                    series=str(definition["series"]),
                    is_active=True,
                )
            for alias in definition["aliases"]:
                ProductAlias.objects.get_or_create(
                    product=product,
                    normalized_alias=_identity(str(alias)),
                    defaults={"alias": str(alias), "source": "SYSTEM"},
                )
            target, _ = SourceTarget.objects.update_or_create(
                source=source,
                name=str(definition["target_name"]),
                defaults={
                    "product": product,
                    "target_type": TargetType.COMMUNITY,
                    "target_url": str(definition["target_url"]),
                    "external_id": str(definition["topic_id"]),
                    "config_json": {"topic_id": int(str(definition["topic_id"]))},
                    "is_active": True,
                },
            )
            CollectionTargetState.objects.get_or_create(source_target=target)
            self.stdout.write(self.style.SUCCESS(f"已确保 {product.name} / {target.target_url}"))
