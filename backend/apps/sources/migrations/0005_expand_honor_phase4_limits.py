from django.db import migrations


TARGET_NAME = "荣耀Power2官方话题"


def update_honor_limits(apps, schema_editor):
    SourceTarget = apps.get_model("sources", "SourceTarget")
    target = SourceTarget.objects.filter(source__code="HONOR_CLUB", name=TARGET_NAME).first()
    if target is None:
        return
    config = dict(target.config_json or {})
    config.update(
        {
            "request_interval_seconds": 3,
            "max_topic_pages": 10,
            "max_threads": 200,
        }
    )
    target.config_json = config
    target.is_active = True
    target.save(update_fields=("config_json", "is_active", "updated_at"))


def restore_honor_limits(apps, schema_editor):
    SourceTarget = apps.get_model("sources", "SourceTarget")
    target = SourceTarget.objects.filter(source__code="HONOR_CLUB", name=TARGET_NAME).first()
    if target is None:
        return
    config = dict(target.config_json or {})
    config.update({"request_interval_seconds": 3, "max_topic_pages": 2, "max_threads": 20})
    target.config_json = config
    target.save(update_fields=("config_json", "updated_at"))


class Migration(migrations.Migration):
    dependencies = [("sources", "0004_source_product_variant_and_jd_target")]

    operations = [migrations.RunPython(update_honor_limits, restore_honor_limits)]
