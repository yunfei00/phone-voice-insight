"""跨来源统一反馈记录。"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from apps.common.models import TimeStampedModel
from apps.products.models import Product, ProductVariant
from apps.sources.models import DataSource, SourceTarget


class RecordType(models.TextChoices):
    REVIEW = "REVIEW", "评价"
    APPEND_REVIEW = "APPEND_REVIEW", "追评"
    THREAD = "THREAD", "帖子"
    REPLY = "REPLY", "回复"
    OFFICIAL_REPLY = "OFFICIAL_REPLY", "官方回复"


class AuthorRole(models.TextChoices):
    USER = "USER", "用户"
    OFFICIAL = "OFFICIAL", "官方"
    UNKNOWN = "UNKNOWN", "未知"


class ReviewStatus(models.TextChoices):
    RAW = "RAW", "原始"
    NORMALIZED = "NORMALIZED", "已标准化"
    INVALID = "INVALID", "无效"


class ReviewRecord(TimeStampedModel):
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="reviews", verbose_name="来源")
    source_target = models.ForeignKey(
        SourceTarget,
        on_delete=models.PROTECT,
        related_name="reviews",
        verbose_name="采集入口",
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="reviews", verbose_name="产品")
    product_variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="reviews",
        null=True,
        blank=True,
        verbose_name="产品版本",
    )
    external_id = models.CharField("外部标识", max_length=255, null=True, blank=True)
    parent_external_id = models.CharField("父记录外部标识", max_length=255, blank=True)
    record_type = models.CharField("记录类型", max_length=30, choices=RecordType.choices)
    title = models.CharField("标题", max_length=500, blank=True)
    content = models.TextField("内容")
    rating = models.DecimalField(
        "评分",
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(5)),
    )
    published_at = models.DateTimeField("发布时间", null=True, blank=True)
    software_version = models.CharField("软件版本", max_length=100, blank=True)
    author_role = models.CharField(
        "作者角色",
        max_length=20,
        choices=AuthorRole.choices,
        default=AuthorRole.UNKNOWN,
    )
    is_official = models.BooleanField("官方内容", default=False)
    is_append_review = models.BooleanField("追评", default=False)
    source_url = models.URLField("来源网址", max_length=1000, blank=True)
    content_hash = models.CharField("内容指纹", max_length=64, db_index=True)
    raw_data = models.JSONField("原始数据", default=dict)
    status = models.CharField("处理状态", max_length=20, choices=ReviewStatus.choices, default=ReviewStatus.RAW)
    collected_at = models.DateTimeField("采集时间")

    class Meta:
        ordering = ("-published_at", "-created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_id", "record_type"),
                condition=Q(external_id__isnull=False) & ~Q(external_id=""),
                name="uniq_review_source_external_type",
            )
        ]
        indexes = [
            models.Index(fields=("source", "record_type", "published_at"), name="review_source_type_time"),
            models.Index(fields=("product", "published_at"), name="review_product_time"),
        ]
        verbose_name = "反馈记录"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.get_record_type_display()} #{self.external_id or self.pk}"
