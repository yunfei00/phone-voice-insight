"""数据来源平台与采集入口。"""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import Product


class SourceType(models.TextChoices):
    ECOMMERCE = "ECOMMERCE", "电商"
    COMMUNITY = "COMMUNITY", "社区"


class DataSource(TimeStampedModel):
    code = models.CharField("编码", max_length=50, unique=True)
    name = models.CharField("名称", max_length=100)
    source_type = models.CharField("来源类型", max_length=20, choices=SourceType.choices)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "数据来源"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.name


class TargetType(models.TextChoices):
    PRODUCT = "PRODUCT", "商品"
    COMMUNITY = "COMMUNITY", "社区入口"


class SourceTarget(TimeStampedModel):
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="targets", verbose_name="来源")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="source_targets", verbose_name="产品")
    name = models.CharField("名称", max_length=150)
    target_type = models.CharField("入口类型", max_length=20, choices=TargetType.choices)
    target_url = models.URLField("目标网址", max_length=1000, blank=True)
    external_id = models.CharField("外部标识", max_length=200, blank=True)
    config_json = models.JSONField("入口配置", default=dict, blank=True)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        ordering = ("source", "name")
        constraints = [models.UniqueConstraint(fields=("source", "name"), name="uniq_source_target_name")]
        verbose_name = "采集入口"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.source.name} - {self.name}"
