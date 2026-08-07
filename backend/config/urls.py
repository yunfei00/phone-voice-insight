"""项目 URL 路由。"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.analysis.views import AnalysisResultViewSet
from apps.collection.views import CollectionTaskViewSet
from apps.common.views import health
from apps.products.views import ProductViewSet
from apps.reviews.views import ReviewRecordViewSet
from apps.sources.views import DataSourceViewSet

router = DefaultRouter()
router.register("products", ProductViewSet, basename="product")
router.register("sources", DataSourceViewSet, basename="source")
router.register("collection-tasks", CollectionTaskViewSet, basename="collection-task")
router.register("reviews", ReviewRecordViewSet, basename="review")
router.register("analysis-results", AnalysisResultViewSet, basename="analysis-result")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
