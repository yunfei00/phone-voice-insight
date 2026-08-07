from django.db import migrations


def seed_products(apps, schema_editor):
    Brand = apps.get_model("products", "Brand")
    Product = apps.get_model("products", "Product")
    ProductAlias = apps.get_model("products", "ProductAlias")
    ProductVariant = apps.get_model("products", "ProductVariant")

    brand, _ = Brand.objects.update_or_create(
        code="HONOR",
        defaults={"name": "荣耀", "is_active": True},
    )
    product, _ = Product.objects.update_or_create(
        normalized_name="HONOR_POWER2",
        defaults={
            "brand": brand,
            "name": "荣耀 Power2",
            "series": "Power",
            "is_active": True,
        },
    )
    aliases = (
        ("荣耀Power2", "荣耀POWER2"),
        ("荣耀 Power2", "荣耀_POWER2"),
        ("荣耀 Power 2", "荣耀_POWER_2"),
        ("HONOR Power2", "HONOR_POWER2"),
        ("Power2", "POWER2"),
    )
    for alias, normalized_alias in aliases:
        ProductAlias.objects.update_or_create(
            product=product,
            normalized_alias=normalized_alias,
            defaults={"alias": alias},
        )

    for storage in ("256GB", "512GB"):
        ProductVariant.objects.update_or_create(
            product=product,
            memory="12GB",
            storage=storage,
            color="",
            defaults={"sku_name": f"12GB+{storage}", "is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_products, migrations.RunPython.noop),
    ]
