# Generated manually for scheduled incremental collection.

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0002_add_incremental_statistics"),
    ]

    operations = [
        migrations.CreateModel(
            name="CollectionSchedule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("enabled", models.BooleanField(default=True, verbose_name="启用")),
                (
                    "interval_hours",
                    models.PositiveSmallIntegerField(
                        default=6,
                        validators=[
                            django.core.validators.MinValueValidator(1),
                            django.core.validators.MaxValueValidator(168),
                        ],
                        verbose_name="增量采集间隔（小时）",
                    ),
                ),
                (
                    "source_target",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="collection_schedule",
                        to="sources.sourcetarget",
                        verbose_name="采集入口",
                    ),
                ),
            ],
            options={
                "verbose_name": "定时采集",
                "verbose_name_plural": "定时采集",
                "ordering": ("source_target__product__name", "source_target__name"),
            },
        ),
    ]
}
