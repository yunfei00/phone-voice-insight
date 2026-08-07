"""采集任务及单次运行记录。"""

from django.core.exceptions import ValidationError
from django.db import models

from apps.common.models import TimeStampedModel
from apps.sources.models import SourceTarget


class CollectionStatus(models.TextChoices):
    PENDING = "PENDING", "待执行"
    RUNNING = "RUNNING", "执行中"
    PAUSED = "PAUSED", "已暂停"
    SUCCESS = "SUCCESS", "成功"
    FAILED = "FAILED", "失败"
    CANCELLED = "CANCELLED", "已取消"


class CollectionTaskType(models.TextChoices):
    FULL = "FULL", "全量"
    INCREMENTAL = "INCREMENTAL", "增量"


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    CollectionStatus.PENDING: {CollectionStatus.RUNNING, CollectionStatus.CANCELLED},
    CollectionStatus.RUNNING: {
        CollectionStatus.PAUSED,
        CollectionStatus.SUCCESS,
        CollectionStatus.FAILED,
        CollectionStatus.CANCELLED,
    },
    CollectionStatus.PAUSED: {CollectionStatus.RUNNING, CollectionStatus.CANCELLED},
    CollectionStatus.SUCCESS: set(),
    CollectionStatus.FAILED: {CollectionStatus.RUNNING},
    CollectionStatus.CANCELLED: set(),
}


class CollectionTask(TimeStampedModel):
    source_target = models.ForeignKey(
        SourceTarget,
        on_delete=models.PROTECT,
        related_name="collection_tasks",
        verbose_name="采集入口",
    )
    task_type = models.CharField(
        "任务类型",
        max_length=20,
        choices=CollectionTaskType.choices,
        default=CollectionTaskType.INCREMENTAL,
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=CollectionStatus.choices,
        default=CollectionStatus.PENDING,
    )
    requested_limit = models.PositiveIntegerField("计划采集条数", null=True, blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    last_checkpoint = models.JSONField("最近检查点", default=dict, blank=True)
    success_count = models.PositiveIntegerField("成功数", default=0)
    skipped_count = models.PositiveIntegerField("跳过数", default=0)
    failure_count = models.PositiveIntegerField("失败数", default=0)
    error_message = models.TextField("错误信息", blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "采集任务"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"#{self.pk} {self.source_target} ({self.status})"

    def transition_to(self, new_status: str) -> None:
        if new_status == self.status:
            return
        if new_status not in ALLOWED_STATUS_TRANSITIONS.get(self.status, set()):
            raise ValidationError(f"采集任务不允许从 {self.status} 转换为 {new_status}")
        self.status = new_status


class CollectionRun(models.Model):
    task = models.ForeignKey(CollectionTask, on_delete=models.CASCADE, related_name="runs", verbose_name="任务")
    run_number = models.PositiveIntegerField("运行序号")
    status = models.CharField("状态", max_length=20, choices=CollectionStatus.choices)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    success_count = models.PositiveIntegerField("成功数", default=0)
    skipped_count = models.PositiveIntegerField("跳过数", default=0)
    failure_count = models.PositiveIntegerField("失败数", default=0)
    checkpoint_json = models.JSONField("检查点", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)

    class Meta:
        ordering = ("task", "-run_number")
        constraints = [models.UniqueConstraint(fields=("task", "run_number"), name="uniq_collection_task_run")]
        verbose_name = "采集运行记录"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"任务 #{self.task_id} / 第 {self.run_number} 次"
