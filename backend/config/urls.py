"""项目 URL 路由。"""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from apps.accounts.views import (
    OllamaModelsView,
    UserAIConfigurationView,
    UserAIConnectivityView,
    UserViewSet,
    change_password,
    login,
    logout,
    me,
    presence_heartbeat,
)
from apps.analysis.structured_views import (
    StructuredAnalysisViewSet,
    StructuredBatchViewSet,
    StructuredRunViewSet,
    TaxonomyViewSet,
)
from apps.analysis.views import AnalysisBatchViewSet, AnalysisResultViewSet
from apps.assistant.views import AssistantConversationViewSet, AssistantModelProfileViewSet, RagIndexViewSet
from apps.collection.views import CollectionScheduleViewSet, CollectionTargetStateViewSet, CollectionTaskViewSet
from apps.common.views import health
from apps.products.views import BrandViewSet, ProductViewSet
from apps.reports.views import (
    DashboardCategoriesView,
    DashboardComparisonView,
    DashboardIssueDetailView,
    DashboardIssueListView,
    DashboardOperationsView,
    DashboardOverviewView,
    DashboardProductsView,
    DashboardReportDetailView,
    DashboardReportGenerateView,
    DashboardReportListView,
    DashboardTrendsView,
    SystemResourcesView,
)
from apps.reviews.ai_views import GovernanceAIViewSet
from apps.reviews.views import ReviewQualityViewSet, ReviewRecordViewSet, ThreadTreeViewSet
from apps.sources.views import DataSourceViewSet, SourceTargetViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("products", ProductViewSet, basename="product")
router.register("brands", BrandViewSet, basename="brand")
router.register("source-targets", SourceTargetViewSet, basename="source-target")
router.register("sources", DataSourceViewSet, basename="source")
router.register("collection-tasks", CollectionTaskViewSet, basename="collection-task")
router.register("collection-schedules", CollectionScheduleViewSet, basename="collection-schedule")
router.register("collection-targets", CollectionTargetStateViewSet, basename="collection-target")
router.register("reviews", ReviewRecordViewSet, basename="review")
router.register("thread-trees", ThreadTreeViewSet, basename="thread-tree")
router.register("review-quality", ReviewQualityViewSet, basename="review-quality")
router.register("governance-ai", GovernanceAIViewSet, basename="governance-ai")
router.register("analysis-results", AnalysisResultViewSet, basename="analysis-result")
router.register("analysis-batches", AnalysisBatchViewSet, basename="analysis-batch")
router.register("structured-runs", StructuredRunViewSet, basename="structured-run")
router.register("structured-analyses", StructuredAnalysisViewSet, basename="structured-analysis")
router.register("structured-batches", StructuredBatchViewSet, basename="structured-batch")
router.register("taxonomies", TaxonomyViewSet, basename="taxonomy")
router.register("assistant/models", AssistantModelProfileViewSet, basename="assistant-model")
router.register("assistant/conversations", AssistantConversationViewSet, basename="assistant-conversation")
router.register("assistant/rag-index", RagIndexViewSet, basename="assistant-rag-index")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/login/", login, name="login"),
    path("api/v1/auth/logout/", logout, name="logout"),
    path("api/v1/auth/me/", me, name="me"),
    path("api/v1/auth/change-password/", change_password, name="change-password"),
    path("api/v1/ai-configuration/", UserAIConfigurationView.as_view(), name="ai-configuration"),
    path("api/v1/ai-configuration/ollama-models/", OllamaModelsView.as_view(), name="ollama-models"),
    path("api/v1/ai-configuration/test/", UserAIConnectivityView.as_view(), name="ai-configuration-test"),
    path("api/v1/dashboard/overview/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    path("api/v1/dashboard/trends/", DashboardTrendsView.as_view(), name="dashboard-trends"),
    path("api/v1/dashboard/categories/", DashboardCategoriesView.as_view(), name="dashboard-categories"),
    path("api/v1/dashboard/products/", DashboardProductsView.as_view(), name="dashboard-products"),
    path("api/v1/dashboard/comparison/", DashboardComparisonView.as_view(), name="dashboard-comparison"),
    path("api/v1/dashboard/issues/", DashboardIssueListView.as_view(), name="dashboard-issues"),
    path(
        "api/v1/dashboard/issues/<path:issue_id>/",
        DashboardIssueDetailView.as_view(),
        name="dashboard-issue-detail",
    ),
    path("api/v1/dashboard/reports/", DashboardReportListView.as_view(), name="dashboard-reports"),
    path(
        "api/v1/dashboard/reports/generate/", DashboardReportGenerateView.as_view(), name="dashboard-reports-generate"
    ),
    path(
        "api/v1/dashboard/reports/<int:report_id>/",
        DashboardReportDetailView.as_view(),
        name="dashboard-report-detail",
    ),
    path("api/v1/dashboard/operations/", DashboardOperationsView.as_view(), name="dashboard-operations"),
    path("api/v1/system/resources/", SystemResourcesView.as_view(), name="system-resources"),
    path("api/v1/presence/heartbeat/", presence_heartbeat, name="presence-heartbeat"),
    path("api/v1/", include(router.urls)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
