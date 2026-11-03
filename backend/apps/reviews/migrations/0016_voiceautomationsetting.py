from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0015_full_ai_progress"),
    ]

    operations = [
        migrations.CreateModel(
            name="VoiceAutomationSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "自动处理设置",
                "verbose_name_plural": "自动处理设置",
            },
        ),
    ]
