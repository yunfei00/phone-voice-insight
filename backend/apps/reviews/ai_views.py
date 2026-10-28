"""AI-assisted governance endpoints."""
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdministrator
from apps.products.models import Product
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview, ReviewQuality
from apps.reviews.services.governance_pipeline import apply_manual_override
from apps.reviews.tasks import process_governance_ai_batch

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

    @action(detail=False, methods=["post"])
    def confirm(self, request):
        class Parameters(serializers.Serializer):
            review_id = serializers.IntegerField(min_value=1)
            eligible = serializers.BooleanField()
            reason = serializers.CharField(min_length=2, max_length=500)

        params = Parameters(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        with transaction.atomic():
            record = GovernanceAIReview.objects.select_for_update().filter(
                quality__review_id=data["review_id"],
                status="REVIEW_REQUIRED", human_reviewed_at__isnull=True
            ).order_by("-id").first()
            if record is None:
                return Response({"detail": "没有待确认的 AI 复核记录"}, status=409)
            apply_manual_override(data["review_id"], eligible=data["eligible"], reason=data["reason"])
            record.human_decision = data["eligible"]
            record.human_reason = data["reason"]
            record.human_reviewer = request.user
            record.human_reviewed_at = timezone.now()
            record.save(update_fields=[
                "human_decision", "human_reason", "human_reviewer", "human_reviewed_at", "updated_at"
            ])
        return Response({"id": record.id, "review_id": data["review_id"], "confirmed": True})

    @action(detail=False, methods=["post"], url_path="retry-failed")
    def retry_failed(self, request):
        batch_id = request.data.get("batch_id")
        try:
            batch_id = int(batch_id)
        except (TypeError, ValueError):
            return Response({"detail": "无效任务编号"}, status=400)
        with transaction.atomic():
            old = GovernanceAIBatch.objects.select_for_update().filter(
                pk=batch_id, requested_by=request.user
            ).first()
            if old is None:
                return Response({"detail": "任务不存在"}, status=404)
            if old.status not in ("FAILED", "PARTIAL"):
                return Response({"detail": "任务当前不可重试"}, status=409)
            ids = list(dict.fromkeys(old.failure_ids or (
                old.quality_ids if old.processed == 0 else []
            )))
            if not ids:
                return Response({"detail": "没有可重试的数据"}, status=409)
            new = GovernanceAIBatch.objects.create(
                product=old.product, requested_by=request.user,
                quality_ids=ids, total=len(ids)
            )
        try:
            job = process_governance_ai_batch.delay(new.id)
            new.celery_task_id = job.id
            new.save(update_fields=["celery_task_id", "updated_at"])
        except Exception:
            new.status = "FAILED"
            new.error_code = "TASK_DISPATCH_FAILED"
            new.save(update_fields=["status", "error_code", "updated_at"])
            return Response({"detail": "重试任务投递失败"}, status=503)
        return Response({"id": new.id, "total": new.total}, status=202)

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
             "model": x.model_name, "human_decision": x.human_decision,
             "human_reviewed_at": x.human_reviewed_at}
            for x in rows
        ]})
