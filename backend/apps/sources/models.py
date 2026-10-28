"""数据来源平台与采集入口。"""

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import Product, ProductVariant


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


class TargetValidationStatus(models.TextChoices):
    UNVERIFIED = "UNVERIFIED", "待验证"
    VALID = "VALID", "验证通过"
    INVALID = "INVALID", "验证失败"


class SourceTarget(TimeStampedModel):
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="targets", verbose_name="来源")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="source_targets", verbose_name="产品")
    name = models.CharField("名称", max_length=150)
    target_type = models.CharField("入口类型", max_length=20, choices=TargetType.choices)
    target_url = models.URLField("目标网址", max_length=1000, blank=True)
    external_id = models.CharField("外部标识", max_length=200, blank=True)
    config_json = models.JSONField("入口配置", default=dict, blank=True)
    is_active = models.BooleanField("启用", default=True)
    validation_status = models.CharField(
        "验证状态",
        max_length=20,
        choices=TargetValidationStatus.choices,
        default=TargetValidationStatus.UNVERIFIED,
    )
    validated_at = models.DateTimeField("验证时间", null=True, blank=True)
    validated_url_hash = models.CharField("已验证网址摘要", max_length=64, blank=True)
    validation_error_code = models.CharField("验证错误编码", max_length=80, blank=True)
    validation_error_message = models.TextField("验证错误", blank=True)
    validation_report = models.JSONField("验证报告", default=dict, blank=True)

    class Meta:
        ordering = ("source", "name")
        constraints = [models.UniqueConstraint(fields=("source", "name"), name="uniq_source_target_name")]
        verbose_name = "采集入口"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.source.name} - {self.name}"


class SourceProductVariant(TimeStampedModel):
    source = models.ForeignKey(
        DataSource,
        on_delete=models.PROTECT,
        related_name="product_variant_mappings",
        verbose_name="来源",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="source_variant_mappings",
        verbose_name="产品",
    )
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="source_mappings",
        verbose_name="产品版本",
    )
    external_id = models.CharField("来源版本标识", max_length=200)
    source_target = models.ForeignKey(
        SourceTarget,
        on_delete=models.PROTECT,
        related_name="variant_mappings",
        null=True,
        blank=True,
        verbose_name="采集入口",
    )
    attributes_json = models.JSONField("来源版本属性", default=dict, blank=True)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        ordering = ("source", "product", "external_id")
        constraints = [
            models.UniqueConstraint(fields=("source", "external_id"), name="uniq_source_variant_external_id")
        ]
        verbose_name = "来源产品版本"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.source.code}:{self.external_id} → {self.product_variant.sku_name}"


class SourceTargetCleanupAudit(models.Model):
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="source_target_cleanup_audits",
        verbose_name="操作人",
    )
    source_target = models.ForeignKey(
        SourceTarget,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cleanup_audits",
        verbose_name="采集入口",
    )
    source_target_id_snapshot = models.PositiveBigIntegerField("入口 ID 快照")
    product_id_snapshot = models.PositiveBigIntegerField("手机 ID 快照")
    product_name = models.CharField("手机名称", max_length=150)
    source_name = models.CharField("来源名称", max_length=100)
    target_url = models.URLField("入口网址", max_length=1000, blank=True)
    result = models.CharField("执行结果", max_length=20)
    deleted_counts = models.JSONField("清理数量", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    created_at = models.DateTimeField("操作时间", auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "采集入口清理审计"
        verbose_name_plural = verbose_name
