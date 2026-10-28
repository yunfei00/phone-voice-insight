"""采集任务及单次运行记录。"""

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
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
    STOPPING = "STOPPING", "停止中"


class CollectionTaskType(models.TextChoices):
    FULL = "FULL", "全量"
    INCREMENTAL = "INCREMENTAL", "增量"


class CollectionTriggerType(models.TextChoices):
    MANUAL = "MANUAL", "手工"
    SCHEDULED = "SCHEDULED", "定时"
    RETRY = "RETRY", "自动重试"
    RECOVERY = "RECOVERY", "恢复"


class CollectionTargetStatus(models.TextChoices):
    NOT_INITIALIZED = "NOT_INITIALIZED", "未初始化"
    WAITING = "WAITING", "等待执行"
    FULL_RUNNING = "FULL_RUNNING", "全量执行中"
    INCREMENTAL_RUNNING = "INCREMENTAL_RUNNING", "增量执行中"
    READY = "READY", "已就绪"
    DEGRADED = "DEGRADED", "异常"


class DiscoveryStatus(models.TextChoices):
    PENDING = "PENDING", "待采集"
    SUCCESS = "SUCCESS", "成功"
    SKIPPED = "SKIPPED", "产品不匹配"
    FAILED = "FAILED", "失败"


ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    CollectionStatus.PENDING: {CollectionStatus.RUNNING, CollectionStatus.CANCELLED},
    CollectionStatus.RUNNING: {
        CollectionStatus.PAUSED,
        CollectionStatus.SUCCESS,
        CollectionStatus.FAILED,
        CollectionStatus.CANCELLED,
        CollectionStatus.STOPPING,
    },
    CollectionStatus.PAUSED: {CollectionStatus.RUNNING, CollectionStatus.CANCELLED, CollectionStatus.STOPPING},
    CollectionStatus.STOPPING: {CollectionStatus.CANCELLED},
    CollectionStatus.SUCCESS: {CollectionStatus.PENDING},
    CollectionStatus.FAILED: {CollectionStatus.PENDING, CollectionStatus.RUNNING},
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
    trigger_type = models.CharField(
        "触发方式",
        max_length=20,
        choices=CollectionTriggerType.choices,
        default=CollectionTriggerType.MANUAL,
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=CollectionStatus.choices,
        default=CollectionStatus.PENDING,
    )
    requested_limit = models.PositiveIntegerField("计划采集条数", null=True, blank=True)
    requested_pages = models.PositiveIntegerField("计划采集页数", null=True, blank=True)
    waiting_reason = models.CharField("等待原因", max_length=120, blank=True)
    dispatch_token = models.UUIDField("派发令牌", null=True, blank=True, editable=False)
    dispatched_at = models.DateTimeField("最近派发时间", null=True, blank=True)
    execution_token = models.UUIDField("执行代次令牌", null=True, blank=True, editable=False)
    heartbeat_at = models.DateTimeField("执行心跳", null=True, blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    last_checkpoint = models.JSONField("最近检查点", default=dict, blank=True)
    success_count = models.PositiveIntegerField("成功数", default=0)
    skipped_count = models.PositiveIntegerField("跳过数", default=0)
    failure_count = models.PositiveIntegerField("失败数", default=0)
    new_threads = models.PositiveIntegerField("新增帖子", default=0)
    known_threads = models.PositiveIntegerField("已知帖子", default=0)
    new_records = models.PositiveIntegerField("新增记录", default=0)
    duplicate_records = models.PositiveIntegerField("重复记录", default=0)
    stopped_at_known_boundary = models.BooleanField("在已知边界停止", default=False)
    error_message = models.TextField("错误信息", blank=True)
    completion_verified = models.BooleanField("完整性验证通过", default=False)
    verification_report = models.JSONField("完整性报告", default=dict, blank=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "采集任务"
        verbose_name_plural = verbose_name
        constraints = [
            models.UniqueConstraint(
                fields=("source_target",),
                condition=models.Q(status__in=("PENDING", "RUNNING", "PAUSED", "STOPPING")),
                name="uniq_active_collection_per_target",
            )
        ]

    def __str__(self) -> str:
        return f"#{self.pk} {self.source_target} ({self.status})"

    def transition_to(self, new_status: str) -> None:
        if new_status == self.status:
            return
        if new_status not in ALLOWED_STATUS_TRANSITIONS.get(self.status, set()):
            raise ValidationError(f"采集任务不允许从 {self.status} 转换为 {new_status}")
        self.status = new_status


class CollectionSchedule(TimeStampedModel):
    source_target = models.OneToOneField(
        SourceTarget,
        on_delete=models.CASCADE,
        related_name="collection_schedule",
        verbose_name="采集入口",
    )
    enabled = models.BooleanField("启用", default=True)
    interval_hours = models.PositiveSmallIntegerField(
        "增量采集间隔(小时)",
        default=6,
        validators=(MinValueValidator(1), MaxValueValidator(168)),
    )

    class Meta:
        ordering = ("source_target__product__name", "source_target__name")
        verbose_name = "定时采集"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"{self.source_target} / 每 {self.interval_hours} 小时"


class CollectionTargetState(TimeStampedModel):
    source_target = models.OneToOneField(
        SourceTarget,
        on_delete=models.CASCADE,
        related_name="collection_state",
        verbose_name="采集入口",
    )
    status = models.CharField(
        "状态",
        max_length=30,
        choices=CollectionTargetStatus.choices,
        default=CollectionTargetStatus.NOT_INITIALIZED,
    )
    full_verified = models.BooleanField("全量完整性验证通过", default=False)
    full_verified_at = models.DateTimeField("全量验证时间", null=True, blank=True)
    active_task = models.ForeignKey(
        CollectionTask,
        on_delete=models.SET_NULL,
        related_name="active_for_states",
        null=True,
        blank=True,
        verbose_name="当前任务",
    )
    last_full_task = models.ForeignKey(
        CollectionTask,
        on_delete=models.SET_NULL,
        related_name="last_full_for_states",
        null=True,
        blank=True,
        verbose_name="最近全量任务",
    )
    last_incremental_task = models.ForeignKey(
        CollectionTask,
        on_delete=models.SET_NULL,
        related_name="last_incremental_for_states",
        null=True,
        blank=True,
        verbose_name="最近增量任务",
    )
    last_success_at = models.DateTimeField("最近成功时间", null=True, blank=True)
    last_failure_at = models.DateTimeField("最近失败时间", null=True, blank=True)
    last_discovered_thread_count = models.PositiveIntegerField("最近发现帖子数", default=0)
    last_verified_thread_count = models.PositiveIntegerField("最近验证帖子数", default=0)
    last_error = models.TextField("最近错误", blank=True)

    class Meta:
        ordering = ("source_target__product__name", "source_target__name")


class CollectionDiscoveredThread(TimeStampedModel):
    task = models.ForeignKey(
        CollectionTask,
        on_delete=models.CASCADE,
        related_name="discovered_threads",
        verbose_name="全量任务",
    )
    thread_id = models.CharField("帖子 ID", max_length=100)
    topic_page = models.PositiveIntegerField("发现页")
    position = models.PositiveIntegerField("页内序号", default=0)
    thread_url = models.URLField("帖子地址", max_length=1000)
    listing_data = models.JSONField("列表元数据", default=dict)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=DiscoveryStatus.choices,
        default=DiscoveryStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField("尝试次数", default=0)
    next_reply_page = models.PositiveIntegerField("下一回复页", default=1)
    expected_reply_pages = models.PositiveIntegerField("预计回复页数", default=0)
    reply_pages_scanned = models.PositiveIntegerField("回复页数", default=0)
    collected_reply_count = models.PositiveIntegerField("采集回复数", default=0)
    source_reported_reply_count = models.PositiveIntegerField("来源回复数", null=True, blank=True)
    last_error = models.TextField("最后错误", blank=True)

    class Meta:
        ordering = ("topic_page", "position", "id")
        constraints = [models.UniqueConstraint(fields=("task", "thread_id"), name="uniq_discovered_task_thread")]
        indexes = [models.Index(fields=("task", "status", "attempts"), name="collect_disc_task_status")]


class CollectionSourceLease(TimeStampedModel):
    source = models.OneToOneField(
        "sources.DataSource",
        on_delete=models.CASCADE,
        related_name="collection_lease",
        verbose_name="来源",
    )
    owner_task = models.ForeignKey(
        CollectionTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="source_leases",
        verbose_name="持有任务",
    )
    expires_at = models.DateTimeField("过期时间", null=True, blank=True)
    owner_token = models.UUIDField("持有代次令牌", null=True, blank=True, editable=False)


class CollectionScheduleEvent(TimeStampedModel):
    schedule = models.ForeignKey(
        CollectionSchedule,
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name="定时配置",
    )
    status = models.CharField("状态", max_length=40)
    reason = models.CharField("原因", max_length=100, blank=True)
    task = models.ForeignKey(CollectionTask, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)


class CollectionRun(models.Model):
    task = models.ForeignKey(CollectionTask, on_delete=models.CASCADE, related_name="runs", verbose_name="任务")
    run_number = models.PositiveIntegerField("运行序号")
    execution_token = models.UUIDField("执行代次令牌", null=True, blank=True, editable=False)
    status = models.CharField("状态", max_length=20, choices=CollectionStatus.choices)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    success_count = models.PositiveIntegerField("成功数", default=0)
    skipped_count = models.PositiveIntegerField("跳过数", default=0)
    failure_count = models.PositiveIntegerField("失败数", default=0)
    new_threads = models.PositiveIntegerField("新增帖子", default=0)
    known_threads = models.PositiveIntegerField("已知帖子", default=0)
    new_records = models.PositiveIntegerField("新增记录", default=0)
    duplicate_records = models.PositiveIntegerField("重复记录", default=0)
    stopped_at_known_boundary = models.BooleanField("在已知边界停止", default=False)
    checkpoint_json = models.JSONField("检查点", default=dict, blank=True)
    error_message = models.TextField("错误信息", blank=True)
    completion_verified = models.BooleanField("完整性验证通过", default=False)
    verification_report = models.JSONField("完整性报告", default=dict, blank=True)

    class Meta:
        ordering = ("task", "-run_number")
        constraints = [models.UniqueConstraint(fields=("task", "run_number"), name="uniq_collection_task_run")]
        verbose_name = "采集运行记录"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return f"任务 #{self.task_id} / 第 {self.run_number} 次"
