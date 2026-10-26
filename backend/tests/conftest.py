import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile, UserRole
from apps.products.models import Brand, Product
from apps.sources.models import DataSource, SourceTarget, SourceType, TargetType


@pytest.fixture
def api_client(db: object) -> APIClient:
    _ = db
    user = get_user_model().objects.create_user(username="test-admin", password="test-password")
    UserProfile.objects.create(user=user, role=UserRole.ADMIN)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def product(db: object) -> Product:
    _ = db
    brand, _ = Brand.objects.update_or_create(code="HONOR", defaults={"name": "荣耀"})
    product, _ = Product.objects.update_or_create(
        normalized_name="HONOR_POWER2",
        defaults={
            "brand": brand,
            "name": "荣耀 Power2",
            "series": "Power",
        },
    )
    return product


@pytest.fixture
def source(db: object) -> DataSource:
    _ = db
    source, _ = DataSource.objects.update_or_create(
        code="JD",
        defaults={"name": "京东", "source_type": SourceType.ECOMMERCE},
    )
    return source


@pytest.fixture
def source_target(product: Product, source: DataSource) -> SourceTarget:
    return SourceTarget.objects.create(
        source=source,
        product=product,
        name="测试入口",
        target_type=TargetType.PRODUCT,
    )
