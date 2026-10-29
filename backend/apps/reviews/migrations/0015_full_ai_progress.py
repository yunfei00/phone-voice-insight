from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0014_governanceaibatch_source"),
    ]

    operations = [
        migrations.AddField(
            model_name="governanceaibatch",
            name="root_batch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="continuations", to="reviews.governanceaibatch"),
        ),
        migrations.AddField(
            model_name="governanceaibatch",
            name="scope_total",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="governanceaibatch",
            name="stop_requested",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="governanceaibatch",
            name="status",
            field=models.CharField(choices=[("PENDING", "等待执行"), ("RUNNING", "执行中"), ("SUCCESS", "完成"), ("PARTIAL", "部分失败"), ("FAILED", "失败"), ("STOPPED", "已停止")], db_index=True, default="PENDING", max_length=16),
        ),
    ]
