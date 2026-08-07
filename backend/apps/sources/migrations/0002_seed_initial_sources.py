from django.db import migrations


def seed_sources(apps, schema_editor):
    DataSource = apps.get_model("sources", "DataSource")
    DataSource.objects.update_or_create(
        code="JD",
        defaults={"name": "京东", "source_type": "ECOMMERCE", "is_active": True},
    )
    DataSource.objects.update_or_create(
        code="HONOR_CLUB",
        defaults={"name": "荣耀俱乐部", "source_type": "COMMUNITY", "is_active": True},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("sources", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_sources, migrations.RunPython.noop),
    ]
