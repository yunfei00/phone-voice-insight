"""结构化分析结果；本阶段只存储契约，不调用模型。"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.common.models import TimeStampedModel
from apps.reviews.models import ReviewRecord


class AnalysisStatus(models.TextChoices):
    PENDING = "PENDING", "待分析"
    SUCCESS = "SUCCESS", "成功"
    FAILED = "FAILED", "失败"


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


class AnalysisResult(TimeStampedModel):
    review = models.ForeignKey(ReviewRecord, on_delete=models.CASCADE, related_name="analyses", verbose_name="反馈")
    status = models.CharField("状态", max_length=20, choices=AnalysisStatus.choices, default=AnalysisStatus.PENDING)
    model_name = models.CharField("模型名称", max_length=100)
    model_version = models.CharField("模型版本", max_length=100)
    prompt_version = models.CharField("Prompt 版本", max_length=100)
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
    analyzed_at = models.DateTimeField("分析时间", null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("review", "model_name", "model_version", "prompt_version"),
                name="uniq_review_analysis_version",
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
