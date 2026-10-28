from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("reviews", "0006_reviewrecord_review_type_parent_and_more")]

    operations = [
        migrations.AddField(model_name="reviewrecord", name="source_region", field=models.CharField(blank=True, db_index=True, default="", max_length=120, verbose_name="公开地域")),
        migrations.AddField(model_name="reviewrecord", name="region_evidence", field=models.CharField(blank=True, default="", max_length=40, verbose_name="地域依据")),
    ]
