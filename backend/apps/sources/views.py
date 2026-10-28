from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from apps.accounts.permissions import IsAdministrator
from apps.collection.models import CollectionTargetState
from apps.sources.models import DataSource, SourceTarget
from apps.sources.serializers import DataSourceSerializer, SourceTargetSerializer
from apps.sources.services.cleanup import CleanupBlocked, cleanup_preview, execute_cleanup
from apps.sources.services.target_validation import validate_source_target


class DataSourceViewSet(ReadOnlyModelViewSet):
    queryset = DataSource.objects.prefetch_related("targets__product")
    serializer_class = DataSourceSerializer
    filterset_fields = ("source_type", "is_active")
    search_fields = ("name", "code")
    ordering_fields = ("name", "created_at")


class SourceTargetViewSet(ModelViewSet):
    queryset = SourceTarget.objects.select_related("product", "source")
    serializer_class = SourceTargetSerializer
    filterset_fields = ("product", "source", "is_active")

    @transaction.atomic
    def perform_create(self, serializer: BaseSerializer[SourceTarget]) -> None:
        target = serializer.save()
        CollectionTargetState.objects.get_or_create(source_target=target)

    @transaction.atomic
    def perform_update(self, serializer: BaseSerializer[SourceTarget]) -> None:
        target = serializer.save()
        CollectionTargetState.objects.get_or_create(source_target=target)

    @action(detail=True, methods=("post",), url_path="validate")
    def validate_target(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        target = self.get_object()
        result = validate_source_target(target)
        response_status = status.HTTP_200_OK if result.valid else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(
            {
                "valid": result.valid,
                "code": result.code,
                "detail": result.message,
                "report": result.report,
                "target": self.get_serializer(target).data,
            },
            status=response_status,
        )

    @action(detail=True, methods=("get",), url_path="cleanup-preview", permission_classes=(IsAdministrator,))
    def cleanup_preview_action(self, request: Request, pk: str | None = None) -> Response:
        del request, pk
        return Response(cleanup_preview(self.get_object()))

    @action(detail=True, methods=("post",), url_path="cleanup", permission_classes=(IsAdministrator,))
    def cleanup_action(self, request: Request, pk: str | None = None) -> Response:
        del pk
        target = self.get_object()
        expected = f"DELETE {target.id}"
        if request.data.get("confirmation") != expected:
            return Response(
                {"code": "CONFIRMATION_REQUIRED", "detail": f"请输入确认文本: {expected}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = execute_cleanup(target.id, request.user)
        except CleanupBlocked as exc:
            return Response({"code": "CLEANUP_BLOCKED", "detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(result)
