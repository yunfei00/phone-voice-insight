"""AI-assisted governance endpoints."""
from django.db import transaction
from rest_framework import serializers, viewsets
from apps.products.models import Product
from apps.reviews.models import ReviewQuality
from apps.reviews.tasks import process_governance_ai_batch
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.accounts.permissions import IsAdministrator
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview

class GovernanceAIViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdministrator]
    queryset = GovernanceAIBatch.objects.all()

    @action(detail=False, methods=["post"])
    def start(self, request):
        class Parameters(serializers.Serializer):
            product_id = serializers.IntegerField(min_value=1)
            limit = serializers.IntegerField(min_value=1, max_value=100, default=20)

        params = Parameters(data=request.data)
        params.is_valid(raise_exception=True)
        product_id = params.validated_data["product_id"]
        limit = params.validated_data["limit"]
        with transaction.atomic():
            product = Product.objects.select_for_update().filter(pk=product_id).first()
            if product is None:
                return Response({"detail": "产品不存在"}, status=404)
            reserved = set()
            for ids in GovernanceAIBatch.objects.filter(
                product=product, status__in=["PENDING", "RUNNING"]
            ).values_list("quality_ids", flat=True):
                reserved.update(ids)
            reviewed_ids = GovernanceAIReview.objects.filter(
                status__in=["SUCCEEDED", "REVIEW_REQUIRED"]
            ).values_list("quality_id", flat=True)
            ids = list(ReviewQuality.objects.filter(review__product=product)
                       .exclude(id__in=reviewed_ids).exclude(id__in=reserved)
                       .order_by("id").values_list("id", flat=True)[:limit])
            if not ids:
                return Response({"detail": "没有待 AI 复核的数据"}, status=409)
            batch = GovernanceAIBatch.objects.create(
                product=product, requested_by=request.user, quality_ids=ids, total=len(ids)
            )
        try:
            job = process_governance_ai_batch.delay(batch.id)
            batch.celery_task_id = job.id
            batch.save(update_fields=["celery_task_id", "updated_at"])
        except Exception:
            batch.status = GovernanceAIBatch.Status.FAILED
            batch.error_code = "TASK_DISPATCH_FAILED"
            batch.save(update_fields=["status", "error_code", "updated_at"])
            return Response({"detail": "AI 任务提交失败"}, status=503)
        return Response({"id": batch.id, "total": batch.total}, status=202)

    @action(detail=False, methods=["get"])
    def history(self, request):
        items = GovernanceAIBatch.objects.filter(requested_by=request.user)[:30]
        return Response({"results": [
            {"id": x.id, "status": x.status, "total": x.total,
             "processed": x.processed, "succeeded": x.succeeded,
             "review_required": x.review_required, "failed": x.failed}
            for x in items
        ]})

    @action(detail=False, methods=["get"])
    def results(self, request):
        try:
            product_id = int(request.query_params["product_id"])
        except (KeyError, ValueError):
            return Response({"detail": "请选择产品"}, status=400)
        rows = GovernanceAIReview.objects.filter(
            quality__review__product_id=product_id
        ).select_related("quality").order_by("-id")[:100]
        return Response({"results": [
            {"id": x.id, "review_id": x.quality.review_id,
             "status": x.status, "rule_eligible": x.rule_eligible,
             "ai_eligible": x.ai_eligible, "confidence": x.confidence,
             "reason": x.reason, "evidence": x.evidence,
             "model": x.model_name}
            for x in rows
        ]})
