import django.db.models.deletion
from django.db import migrations, models


TARGET_NAME = "荣耀Power2京东自营"


def seed_jd_target(apps, schema_editor):
    DataSource = apps.get_model("sources", "DataSource")
    Product = apps.get_model("products", "Product")
    SourceTarget = apps.get_model("sources", "SourceTarget")

    source = DataSource.objects.get(code="JD")
    product = Product.objects.get(normalized_name="HONOR_POWER2")
    SourceTarget.objects.update_or_create(
        source=source,
        name=TARGET_NAME,
        defaults={
            "product": product,
            "target_type": "PRODUCT",
            "target_url": "https://item.jd.com/100310496358.html",
            "external_id": "jd:100310496358",
            "config_json": {
                "product_id": "100310496358",
                "request_interval_seconds": 4,
                "max_pages": 3,
                "page_size": 10,
                "shop_type": "JD_SELF_OPERATED",
            },
            # 2026-08-08 正常浏览被登录墙阻断；完成商品/店铺/接口复验前保持停用。
            "is_active": False,
        },
    )


def remove_jd_target(apps, schema_editor):
    SourceTarget = apps.get_model("sources", "SourceTarget")
    SourceTarget.objects.filter(source__code="JD", name=TARGET_NAME, external_id="jd:100310496358").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_seed_initial_products"),
        ("sources", "0003_seed_honor_power2_target"),
    ]

    operations = [
        migrations.CreateModel(
            name="SourceProductVariant",
            fields=[
                (
                    "id",
                    models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="创建时间")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="更新时间")),
                ("external_id", models.CharField(max_length=200, verbose_name="来源版本标识")),
                ("attributes_json", models.JSONField(blank=True, default=dict, verbose_name="来源版本属性")),
                ("is_active", models.BooleanField(default=True, verbose_name="启用")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="source_variant_mappings",
                        to="products.product",
                        verbose_name="产品",
                    ),
                ),
                (
                    "product_variant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="source_mappings",
                        to="products.productvariant",
                        verbose_name="产品版本",
                    ),
                ),
                (
                    "source",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="product_variant_mappings",
                        to="sources.datasource",
                        verbose_name="来源",
                    ),
                ),
                (
                    "source_target",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="variant_mappings",
                        to="sources.sourcetarget",
                        verbose_name="采集入口",
                    ),
                ),
            ],
            options={
                "verbose_name": "来源产品版本",
                "verbose_name_plural": "来源产品版本",
                "ordering": ("source", "product", "external_id"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("source", "external_id"), name="uniq_source_variant_external_id"
                    )
                ],
            },
        ),
        migrations.RunPython(seed_jd_target, remove_jd_target),
    ]
