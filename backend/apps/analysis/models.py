"""可追溯的结构化 AI 分析、批次和人工评估。"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import Product
from apps.reviews.models import AnalysisCorpusItem, ContentPurpose, ReviewRecord
from apps.sources.models import DataSource


class AnalysisStatus(models.TextChoices):
    PENDING = "PENDING", "待分析"
    SUCCESS = "SUCCESS", "成功"
    FAILED = "FAILED", "失败"


class AnalysisBatchStatus(models.TextChoices):
    PENDING = "PENDING", "待执行"
    RUNNING = "RUNNING", "执行中"
    SUCCESS = "SUCCESS", "成功"
    PARTIAL = "PARTIAL", "部分成功"
    FAILED = "FAILED", "失败"
    CANCELLED = "CANCELLED", "已取消"


class Aspect(models.TextChoices):
    BATTERY = "BATTERY", "续航"
    CHARGING = "CHARGING", "充电"
    HEATING = "HEATING", "发热"
    SIGNAL = "SIGNAL", "信号"
    PERFORMANCE = "PERFORMANCE", "性能"
    SYSTEM_FLUENCY = "SYSTEM_FLUENCY", "系统流畅度"
    SYSTEM_BUG = "SYSTEM_BUG", "系统问题"
    DISPLAY = "DISPLAY", "屏幕"
    CAMERA = "CAMERA", "影像"
    WEIGHT_AND_FEEL = "WEIGHT_AND_FEEL", "重量与手感"
    BUILD_QUALITY = "BUILD_QUALITY", "做工"
    AUDIO_AND_CALL = "AUDIO_AND_CALL", "音频与通话"
    DURABILITY = "DURABILITY", "耐用性"
    VALUE_FOR_MONEY = "VALUE_FOR_MONEY", "性价比"
    AFTER_SALES = "AFTER_SALES", "售后"


class Sentiment(models.TextChoices):
    POSITIVE = "POSITIVE", "正面"
    NEUTRAL = "NEUTRAL", "中性"
    NEGATIVE = "NEGATIVE", "负面"
    MIXED = "MIXED", "混合"


class AnalysisBatch(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="analysis_batches", verbose_name="产品")
    source = models.ForeignKey(
        DataSource, on_delete=models.PROTECT, related_name="analysis_batches", verbose_name="来源"
    )
    corpus_version = models.CharField("语料版本", max_length=80)
    provider = models.CharField("Provider", max_length=80)
    model_name = models.CharField("模型名称", max_length=150)
    prompt_version = models.CharField("Prompt 版本", max_length=100)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=AnalysisBatchStatus.choices,
        default=AnalysisBatchStatus.PENDING,
    )
    requested_count = models.PositiveIntegerField("计划数量", default=0)
    success_count = models.PositiveIntegerField("成功数量", default=0)
    failed_count = models.PositiveIntegerField("失败数量", default=0)
    skipped_count = models.PositiveIntegerField("跳过数量", default=0)
    retry_count = models.PositiveIntegerField("重试数量", default=0)
    prompt_tokens = models.PositiveBigIntegerField("Prompt Tokens", null=True, blank=True)
    completion_tokens = models.PositiveBigIntegerField("Completion Tokens", null=True, blank=True)
    total_tokens = models.PositiveBigIntegerField("Total Tokens", null=True, blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    error_message = models.TextField("安全错误信息", blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "AI 分析批次"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"批次 #{self.pk} / {self.status}"


class AnalysisResult(TimeStampedModel):
    review = models.ForeignKey(ReviewRecord, on_delete=models.CASCADE, related_name="analyses", verbose_name="反馈")
    corpus_item = models.ForeignKey(
        AnalysisCorpusItem,
        on_delete=models.PROTECT,
        related_name="analyses",
        null=True,
        blank=True,
        verbose_name="分析语料",
    )
    batch = models.ForeignKey(
        AnalysisBatch,
        on_delete=models.SET_NULL,
        related_name="results",
        null=True,
        blank=True,
        verbose_name="分析批次",
    )
    status = models.CharField("状态", max_length=20, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING)
    provider = models.CharField("Provider", max_length=80, default="")
    model_name = models.CharField("模型名称", max_length=100)
    model_version = models.CharField("模型版本", max_length=100)
    prompt_version = models.CharField("Prompt 版本", max_length=100)
    input_hash = models.CharField("输入指纹", max_length=64, db_index=True, default="")
    content_purpose = models.CharField(
        "内容用途",
        max_length=30,
        choices=ContentPurpose.choices,
        default=ContentPurpose.OTHER,
        db_index=True,
    )
    is_valid_content = models.BooleanField("有效内容", default=False)
    confidence = models.DecimalField(
        "置信度",
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    summary = models.TextField("摘要", blank=True)
    raw_result = models.JSONField("原始结果", default=dict, blank=True)
    error_code = models.CharField("错误编码", max_length=80, blank=True, db_index=True)
    error_message = models.TextField("安全错误信息", blank=True)
    attempt_count = models.PositiveIntegerField("调用次数", default=0)
    retry_count = models.PositiveIntegerField("重试次数", default=0)
    latency_ms = models.PositiveIntegerField("耗时毫秒", null=True, blank=True)
    prompt_tokens = models.PositiveIntegerField("Prompt Tokens", null=True, blank=True)
    completion_tokens = models.PositiveIntegerField("Completion Tokens", null=True, blank=True)
    total_tokens = models.PositiveIntegerField("Total Tokens", null=True, blank=True)
    provider_request_id = models.CharField("Provider Request ID", max_length=200, blank=True)
    analyzed_at = models.DateTimeField("分析时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("review", "provider", "model_name", "prompt_version", "input_hash"),
                name="uniq_review_analysis_input",
            )
        ]
        verbose_name = "分析结果"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"反馈 #{self.review_id} / {self.model_name}"


class AspectResult(models.Model):
    analysis = models.ForeignKey(AnalysisResult, on_delete=models.CASCADE, related_name="aspects", verbose_name="分析")
    aspect = models.CharField("维度", max_length=30, choices=Aspect.choices)
    sentiment = models.CharField("情感", max_length=20, choices=Sentiment.choices)
    sentiment_score = models.DecimalField(
        "情感分",
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        validators=(MinValueValidator(-1), MaxValueValidator(1)),
    )
    issue_category = models.CharField("问题分类", max_length=100, blank=True)
    issue_summary = models.CharField("问题摘要", max_length=500, blank=True)
    usage_scenario = models.CharField("使用场景", max_length=200, blank=True)
    evidence_text = models.TextField("证据片段")
    context_dependent = models.BooleanField("依赖上下文", default=False)
    context_evidence_text = models.TextField("上下文证据", blank=True)
    context_evidence_review_id = models.CharField("上下文证据记录 ID", max_length=80, blank=True)
    confidence = models.DecimalField(
        "置信度",
        max_digits=4,
        decimal_places=3,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )

    class Meta:
        ordering = ("analysis", "aspect")
        verbose_name = "维度分析结果"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.get_aspect_display()} / {self.get_sentiment_display()}"


class AnalysisEvaluation(TimeStampedModel):
    analysis = models.OneToOneField(
        AnalysisResult,
        on_delete=models.CASCADE,
        related_name="evaluation",
        verbose_name="分析结果",
    )
    aspect_correct = models.BooleanField("维度正确")
    sentiment_correct = models.BooleanField("情感正确")
    issue_correct = models.BooleanField("问题正确")
    scenario_correct = models.BooleanField("场景正确")
    evidence_correct = models.BooleanField("证据正确")
    context_correct = models.BooleanField("上下文使用正确")
    hallucination = models.BooleanField("存在严重幻觉", default=False)
    reviewer_notes = models.TextField("审核备注", blank=True)
    evaluated_at = models.DateTimeField("审核时间")

    class Meta:
        ordering = ("-evaluated_at",)
        verbose_name = "AI 分析人工评估"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"分析 #{self.analysis_id} 人工评估"
