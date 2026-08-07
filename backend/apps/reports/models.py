"""报告快照的最小模型，生成逻辑留待后续阶段。"""

from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import Product


class ReportStatus(models.TextChoices):
    PENDING = "PENDING", "待生成"
    READY = "READY", "已生成"
    FAILED = "FAILED", "失败"


class AggregateReport(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="reports", verbose_name="产品")
    title = models.CharField("标题", max_length=200)
    period_start = models.DateTimeField("统计开始时间")
    period_end = models.DateTimeField("统计结束时间")
    status = models.CharField("状态", max_length=20, choices=ReportStatus.choices, default=ReportStatus.PENDING)
    snapshot = models.JSONField("报告快照", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)

    class Meta:
        ordering = ("-period_end",)
        verbose_name = "聚合报告"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.title
