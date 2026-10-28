from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("reviews", "0008_governancetask")]

    operations = [
        migrations.CreateModel(
            name="GovernanceAIReview",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("status", models.CharField(choices=[("PENDING", "待复核"), ("SUCCEEDED", "复核完成"), ("REVIEW_REQUIRED", "需要人工确认"), ("FAILED", "调用失败")], db_index=True, default="PENDING", max_length=24)),
                ("rule_eligible", models.BooleanField()),
                ("ai_eligible", models.BooleanField(blank=True, null=True)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("reason", models.TextField(blank=True)),
                ("evidence", models.TextField(blank=True)),
                ("provider", models.CharField(blank=True, max_length=64)),
                ("model_name", models.CharField(blank=True, max_length=128)),
                ("prompt_version", models.CharField(default="governance_review_v1", max_length=40)),
                ("input_hash", models.CharField(db_index=True, max_length=64)),
                ("raw_response", models.JSONField(default=dict)),
                ("error_code", models.CharField(blank=True, max_length=80)),
                ("prompt_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("completion_tokens", models.PositiveIntegerField(blank=True, null=True)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("quality", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ai_reviews", to="reviews.reviewquality")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(
            model_name="governanceaireview",
            index=models.Index(fields=["quality", "input_hash"], name="gov_ai_quality_hash"),
        ),
    ]
