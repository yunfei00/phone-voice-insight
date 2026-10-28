from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("collection", "0007_collection_stop_state")]

    operations = [
        migrations.AddField(
            model_name="collectiontask",
            name="requested_pages",
            field=models.PositiveIntegerField("计划采集页数", null=True, blank=True),
        ),
    ]
