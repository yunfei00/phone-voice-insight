from django.db import migrations


TARGET_NAME = "荣耀Power2官方话题"


def seed_honor_power2_target(apps, schema_editor):
    DataSource = apps.get_model("sources", "DataSource")
    Product = apps.get_model("products", "Product")
    SourceTarget = apps.get_model("sources", "SourceTarget")

    source = DataSource.objects.get(code="HONOR_CLUB")
    product = Product.objects.get(normalized_name="HONOR_POWER2")
    SourceTarget.objects.update_or_create(
        source=source,
        name=TARGET_NAME,
        defaults={
            "product": product,
            "target_type": "COMMUNITY",
            "target_url": "https://club.honor.com/cn/threadtopic-595-1.html",
            "external_id": "topic:595",
            "config_json": {
                "topic_id": 595,
                "request_interval_seconds": 3,
                "max_topic_pages": 1,
                "max_threads": 10,
            },
            "is_active": True,
        },
    )


def remove_honor_power2_target(apps, schema_editor):
    SourceTarget = apps.get_model("sources", "SourceTarget")
    SourceTarget.objects.filter(
        source__code="HONOR_CLUB",
        name=TARGET_NAME,
        external_id="topic:595",
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_seed_initial_products"),
        ("sources", "0002_seed_initial_sources"),
    ]

    operations = [
        migrations.RunPython(seed_honor_power2_target, remove_honor_power2_target),
    ]
