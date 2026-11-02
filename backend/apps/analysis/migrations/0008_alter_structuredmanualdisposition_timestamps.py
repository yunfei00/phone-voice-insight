from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0007_structuredmanualdisposition"),
    ]

    operations = [
        migrations.AlterField(
            model_name="structuredmanualdisposition",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="创建时间"),
        ),
        migrations.AlterField(
            model_name="structuredmanualdisposition",
            name="updated_at",
            field=models.DateTimeField(auto_now=True, verbose_name="更新时间"),
        ),
    ]
