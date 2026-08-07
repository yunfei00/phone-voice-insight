import pytest
from rest_framework.test import APIClient

from apps.products.models import Product


@pytest.mark.django_db
def test_product_can_be_created(product: Product) -> None:
    assert product.brand.code == "HONOR"
    assert product.normalized_name == "HONOR_POWER2"


@pytest.mark.django_db
def test_product_list_api(api_client: APIClient, product: Product) -> None:
    response = api_client.get("/api/v1/products/")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert response.json()["results"][0]["name"] == product.name
