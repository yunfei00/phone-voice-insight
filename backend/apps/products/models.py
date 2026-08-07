"""品牌、产品、别名与 SKU 模型。"""

from django.db import models

from apps.common.models import TimeStampedModel


class Brand(TimeStampedModel):
    name = models.CharField("名称", max_length=100)
    code = models.CharField("编码", max_length=50, unique=True)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        ordering = ("name",)
        verbose_name = "品牌"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.name


class Product(TimeStampedModel):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products", verbose_name="品牌")
    name = models.CharField("名称", max_length=150)
    normalized_name = models.CharField("标准名称", max_length=150, unique=True)
    series = models.CharField("系列", max_length=100)
    model_code = models.CharField("型号编码", max_length=100, blank=True)
    release_date = models.DateField("发布日期", null=True, blank=True)
    description = models.TextField("描述", blank=True)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        ordering = ("brand__name", "name")
        verbose_name = "手机产品"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.name


class ProductAlias(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="aliases", verbose_name="产品")
    alias = models.CharField("别名", max_length=150)
    normalized_alias = models.CharField("标准化别名", max_length=150)
    source = models.CharField("别名来源", max_length=50, blank=True)

    class Meta:
        ordering = ("alias",)
        constraints = [
            models.UniqueConstraint(fields=("product", "normalized_alias"), name="uniq_product_normalized_alias")
        ]
        verbose_name = "产品别名"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.alias


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants", verbose_name="产品")
    memory = models.CharField("内存", max_length=30)
    storage = models.CharField("存储", max_length=30)
    color = models.CharField("颜色", max_length=50, blank=True)
    sku_name = models.CharField("SKU 名称", max_length=150)
    is_active = models.BooleanField("启用", default=True)

    class Meta:
        ordering = ("product", "memory", "storage", "color")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "memory", "storage", "color"),
                name="uniq_product_variant_spec",
            )
        ]
        verbose_name = "产品版本"
        verbose_name_plural = verbose_name

    def __str__(self) -> str:
        return self.sku_name
