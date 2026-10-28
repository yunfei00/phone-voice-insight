from rest_framework.viewsets import ModelViewSet

from apps.products.models import Brand, Product
from apps.products.serializers import BrandSerializer, ProductSerializer


class ProductViewSet(ModelViewSet):
    queryset = Product.objects.select_related("brand").prefetch_related("aliases", "variants")
    serializer_class = ProductSerializer
    filterset_fields = ("brand", "series", "is_active")
    search_fields = ("name", "normalized_name", "model_code", "aliases__alias")
    ordering_fields = ("name", "release_date", "created_at")


class BrandViewSet(ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
