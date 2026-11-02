from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0006_analysisbatch_input_cost_per_million_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StructuredManualDisposition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(max_length=20, default="IN_REVIEW", choices=[("IN_REVIEW", "待人工处理"), ("DEFERRED", "暂缓"), ("EXCLUDED", "排除"), ("SUBMITTED", "待审核"), ("APPROVED", "已审核")])),
                ("failure_category", models.CharField(max_length=40, default="UNKNOWN")),
                ("reason", models.TextField(blank=True)),
                ("annotation", models.JSONField(default=dict, blank=True)),
                ("reviewed_at", models.DateTimeField(null=True, blank=True)),
                ("content", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="manual_structured_disposition", to="reviews.reviewrecord")),
                ("handler", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="manual_structured_handled", to=settings.AUTH_USER_MODEL)),
                ("reviewer", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.SET_NULL, related_name="manual_structured_approved", to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
