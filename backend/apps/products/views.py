from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.products.models import Product
from apps.products.serializers import ProductSerializer


class ProductViewSet(ReadOnlyModelViewSet):
    queryset = Product.objects.select_related("brand").prefetch_related("aliases", "variants")
    serializer_class = ProductSerializer
    filterset_fields = ("brand", "series", "is_active")
    search_fields = ("name", "normalized_name", "model_code", "aliases__alias")
    ordering_fields = ("name", "release_date", "created_at")
