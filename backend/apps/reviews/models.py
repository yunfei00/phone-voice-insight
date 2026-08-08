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
    MODERATOR = "MODERATOR", "版主"
    EXPERT = "EXPERT", "达人"
    UNKNOWN = "UNKNOWN", "未知"


class ReviewStatus(models.TextChoices):
    RAW = "RAW", "原始"
    NORMALIZED = "NORMALIZED", "已标准化"
    INVALID = "INVALID", "无效"


class ExclusionReason(models.TextChoices):
    NONE = "NONE", "不排除"
    EMPTY_CONTENT = "EMPTY_CONTENT", "空内容"
    OFFICIAL_CONTENT = "OFFICIAL_CONTENT", "官方内容"
    PRODUCT_NOT_MATCHED = "PRODUCT_NOT_MATCHED", "产品不相关"
    PAGE_NOISE = "PAGE_NOISE", "页面噪声"
    PROMOTIONAL = "PROMOTIONAL", "宣传内容"
    LOW_INFORMATION = "LOW_INFORMATION", "低信息"
    DUPLICATE = "DUPLICATE", "重复"
    INVALID_ENCODING = "INVALID_ENCODING", "无效编码"
    PARSER_ARTIFACT = "PARSER_ARTIFACT", "解析残留"
    OTHER = "OTHER", "其他"


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


class ReviewQuality(TimeStampedModel):
    review = models.OneToOneField(
        ReviewRecord,
        on_delete=models.CASCADE,
        related_name="quality",
        verbose_name="反馈记录",
    )
    normalized_text = models.TextField("标准化文本", blank=True)
    has_meaningful_text = models.BooleanField("包含有效文本", default=False)
    is_product_related = models.BooleanField("产品相关", default=False)
    is_official_content = models.BooleanField("官方内容", default=False)
    is_low_information = models.BooleanField("低信息", default=False)
    is_navigation_or_page_noise = models.BooleanField("页面噪声", default=False)
    is_promotional = models.BooleanField("宣传内容", default=False)
    is_duplicate = models.BooleanField("重复", default=False)
    duplicate_of = models.ForeignKey(
        ReviewRecord,
        on_delete=models.SET_NULL,
        related_name="duplicate_quality_records",
        null=True,
        blank=True,
        verbose_name="重复于",
    )
    eligible_for_ai = models.BooleanField("AI 语料可用", default=False, db_index=True)
    exclusion_reason = models.CharField(
        "排除原因",
        max_length=30,
        choices=ExclusionReason.choices,
        default=ExclusionReason.NONE,
        db_index=True,
    )
    quality_score = models.FloatField(
        "语料质量分",
        default=0.0,
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0)),
    )
    flags_json = models.JSONField("规则标记", default=dict, blank=True)
    processor_version = models.CharField("处理器版本", max_length=50, db_index=True)
    processed_at = models.DateTimeField("处理时间")
    manual_override = models.BooleanField("人工覆盖", default=False)
    manual_eligible = models.BooleanField("人工可用判断", null=True, blank=True)
    manual_reason = models.TextField("人工覆盖原因", blank=True)

    class Meta:
        ordering = ("-processed_at", "-id")
        indexes = [
            models.Index(fields=("exclusion_reason", "quality_score"), name="quality_reason_score"),
            models.Index(fields=("processor_version", "eligible_for_ai"), name="quality_version_eligible"),
        ]
        verbose_name = "反馈数据质量"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"反馈 #{self.review_id} / {self.exclusion_reason}"


class ReviewQualityRun(TimeStampedModel):
    review = models.ForeignKey(
        ReviewRecord,
        on_delete=models.CASCADE,
        related_name="quality_runs",
        verbose_name="反馈记录",
    )
    processor_version = models.CharField("处理器版本", max_length=50)
    normalized_text = models.TextField("标准化文本", blank=True)
    eligible_for_ai = models.BooleanField("AI 语料可用", default=False)
    exclusion_reason = models.CharField(
        "排除原因",
        max_length=30,
        choices=ExclusionReason.choices,
        default=ExclusionReason.NONE,
    )
    quality_score = models.FloatField(
        "语料质量分",
        default=0.0,
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0)),
    )
    flags_json = models.JSONField("规则标记", default=dict, blank=True)
    processed_at = models.DateTimeField("处理时间")

    class Meta:
        ordering = ("review_id", "-processed_at")
        constraints = [
            models.UniqueConstraint(
                fields=("review", "processor_version"),
                name="uniq_quality_run_review_version",
            )
        ]
        verbose_name = "反馈治理版本记录"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"反馈 #{self.review_id} / {self.processor_version}"


class AnalysisCorpusItem(TimeStampedModel):
    review = models.OneToOneField(
        ReviewRecord,
        on_delete=models.CASCADE,
        related_name="corpus_item",
        verbose_name="反馈记录",
    )
    quality = models.OneToOneField(
        ReviewQuality,
        on_delete=models.CASCADE,
        related_name="corpus_item",
        verbose_name="治理结果",
    )
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="corpus_items", verbose_name="产品")
    source = models.ForeignKey(DataSource, on_delete=models.PROTECT, related_name="corpus_items", verbose_name="来源")
    record_type = models.CharField("记录类型", max_length=30, choices=RecordType.choices)
    author_role = models.CharField("作者角色", max_length=20, choices=AuthorRole.choices)
    normalized_text = models.TextField("标准化文本", blank=True)
    context_text = models.TextField("分析上下文", blank=True)
    eligible = models.BooleanField("可用于 AI", default=False, db_index=True)
    exclusion_reason = models.CharField(
        "排除原因",
        max_length=30,
        choices=ExclusionReason.choices,
        default=ExclusionReason.NONE,
        db_index=True,
    )
    quality_score = models.FloatField(
        "语料质量分",
        default=0.0,
        validators=(MinValueValidator(0.0), MaxValueValidator(1.0)),
    )
    corpus_version = models.CharField("语料版本", max_length=80, db_index=True)

    class Meta:
        ordering = ("review_id",)
        indexes = [
            models.Index(fields=("product", "corpus_version", "eligible"), name="corpus_product_version"),
            models.Index(fields=("source", "record_type", "eligible"), name="corpus_source_type"),
        ]
        verbose_name = "AI 分析语料"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"语料 #{self.review_id} / {self.corpus_version}"
