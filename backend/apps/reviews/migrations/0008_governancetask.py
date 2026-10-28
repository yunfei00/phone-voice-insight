from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0007_reviewrecord_source_region"),
        ("products", "0001_initial"),
        ("sources", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GovernanceTask",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("status", models.CharField(choices=[("PENDING", "等待执行"), ("RUNNING", "正在执行"), ("SUCCESS", "已完成"), ("PARTIAL", "部分失败"), ("FAILED", "失败")], db_index=True, default="PENDING", max_length=16)),
                ("celery_task_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("review_ids", models.JSONField(default=list)),
                ("reprocess", models.BooleanField(default=False)),
                ("total", models.PositiveIntegerField(default=0)),
                ("processed", models.PositiveIntegerField(default=0)),
                ("eligible", models.PositiveIntegerField(default=0)),
                ("excluded", models.PositiveIntegerField(default=0)),
                ("reused", models.PositiveIntegerField(default=0)),
                ("failed", models.PositiveIntegerField(default=0)),
                ("failures", models.JSONField(default=list)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="governance_tasks", to="products.product")),
                ("source", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to="sources.datasource")),
                ("requested_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
    ]
