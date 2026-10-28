from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("collection", "0006_collectiontask_uniq_active_collection_per_target")]

    operations = [
        migrations.AlterField(
            model_name="collectiontask",
            name="status",
            field=models.CharField(
                "状态", max_length=20, default="PENDING",
                choices=[("PENDING", "待执行"), ("RUNNING", "执行中"),
                         ("PAUSED", "已暂停"), ("SUCCESS", "成功"),
                         ("FAILED", "失败"), ("CANCELLED", "已取消"),
                         ("STOPPING", "停止中")],
            ),
        ),
        migrations.AlterField(
            model_name="collectionrun",
            name="status",
            field=models.CharField(
                "状态", max_length=20,
                choices=[("PENDING", "待执行"), ("RUNNING", "执行中"),
                         ("PAUSED", "已暂停"), ("SUCCESS", "成功"),
                         ("FAILED", "失败"), ("CANCELLED", "已取消"),
                         ("STOPPING", "停止中")],
            ),
        ),
        migrations.RemoveConstraint(model_name="collectiontask", name="uniq_active_collection_per_target"),
        migrations.AddConstraint(
            model_name="collectiontask",
            constraint=models.UniqueConstraint(
                fields=("source_target",),
                condition=Q(status__in=("PENDING", "RUNNING", "PAUSED", "STOPPING")),
                name="uniq_active_collection_per_target",
            ),
        ),
    ]
