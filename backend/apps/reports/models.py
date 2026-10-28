"""确定性用户声音日报与周报快照。"""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import Product
from apps.sources.models import DataSource


class ReportStatus(models.TextChoices):
    PENDING = "PENDING", "待生成"
    READY = "READY", "已生成"
    FAILED = "FAILED", "失败"


class ReportType(models.TextChoices):
    DAILY = "DAILY", "每日用户声音摘要"
    WEEKLY = "WEEKLY", "最近 7 日趋势报告"


class AggregateReport(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="reports",
        null=True,
        blank=True,
        verbose_name="产品",
    )
    source = models.ForeignKey(
        DataSource,
        on_delete=models.PROTECT,
        related_name="reports",
        null=True,
        blank=True,
        verbose_name="来源",
    )
    report_type = models.CharField(
        "报告类型", max_length=20, choices=ReportType.choices, default=ReportType.DAILY, db_index=True
    )
    title = models.CharField("标题", max_length=200)
    period_start = models.DateTimeField("统计开始时间")
    period_end = models.DateTimeField("统计结束时间")
    generated_at = models.DateTimeField("生成时间", null=True, blank=True)
    data_cutoff = models.DateTimeField("数据统计截止时间", null=True, blank=True)
    status = models.CharField("状态", max_length=20, choices=ReportStatus.choices, default=ReportStatus.PENDING)
    snapshot = models.JSONField("报告快照", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)

    class Meta:
        ordering = ("-period_end",)
        indexes = [models.Index(fields=("report_type", "product", "period_end"), name="report_type_product_end")]
        verbose_name = "聚合报告"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.title
