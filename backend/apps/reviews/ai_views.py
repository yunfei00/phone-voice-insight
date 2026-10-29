"""AI-assisted governance endpoints."""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.response import Response

from apps.accounts.permissions import IsAdministrator
from apps.products.models import Product
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview, ReviewQuality
from apps.reviews.services.governance_pipeline import apply_manual_override
from apps.reviews.tasks import process_governance_ai_batch


class GovernancePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class GovernanceAIViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdministrator]
    queryset = GovernanceAIBatch.objects.all()

    @action(detail=False, methods=["post"])
    def start(self, request: Request) -> Response:
        class Parameters(serializers.Serializer):
            product_id = serializers.IntegerField(min_value=1)
            source_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)
            limit = serializers.IntegerField(min_value=1, max_value=100, default=20)

        params = Parameters(data=request.data)
        params.is_valid(raise_exception=True)
        product_id = params.validated_data["product_id"]
        source_id = params.validated_data.get("source_id")
        limit = params.validated_data["limit"]
        user_id = request.user.pk
        if user_id is None:
            return Response({"detail": "用户身份无效"}, status=403)
        with transaction.atomic():
            product = Product.objects.select_for_update().filter(pk=product_id).first()
            if product is None:
                return Response({"detail": "产品不存在"}, status=404)
            reserved = set()
            for ids in GovernanceAIBatch.objects.filter(product=product, status__in=["PENDING", "RUNNING"]).values_list(
                "quality_ids", flat=True
            ):
                reserved.update(ids)
            reviewed_ids = GovernanceAIReview.objects.filter(
                status__in=["ACCEPTED", "REJECTED", "UNCERTAIN", "SUCCEEDED", "REVIEW_REQUIRED"]
            ).values_list("quality_id", flat=True)
            quality_rows = ReviewQuality.objects.filter(review__product=product)
            if source_id is not None:
                quality_rows = quality_rows.filter(review__source_id=source_id)
            ids = list(
                quality_rows.exclude(id__in=reviewed_ids)
                .exclude(id__in=reserved)
                .order_by("id")
                .values_list("id", flat=True)[:limit]
            )
            if not ids:
                return Response({"detail": "没有待 AI 复核的数据"}, status=409)
            batch = GovernanceAIBatch.objects.create(
                product=product,
                source_id=source_id,
                requested_by_id=user_id,
                quality_ids=ids,
                total=len(ids),
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

    @action(detail=False, methods=["post"], url_path="start-full")
    def start_full(self, request: Request) -> Response:
        """Start bounded, sequential AI batches for the entire remaining scope."""
        class Parameters(serializers.Serializer):
            product_id = serializers.IntegerField(min_value=1)
            source_id = serializers.IntegerField(min_value=1, required=False, allow_null=True)

        params = Parameters(data=request.data)
        params.is_valid(raise_exception=True)
        product_id = params.validated_data["product_id"]
        source_id = params.validated_data.get("source_id")
        user_id = request.user.pk
        if user_id is None:
            return Response({"detail": "用户身份无效"}, status=403)
        with transaction.atomic():
            product = Product.objects.select_for_update().filter(pk=product_id).first()
            if product is None:
                return Response({"detail": "产品不存在"}, status=404)
            if GovernanceAIBatch.objects.filter(
                product=product, status__in=["PENDING", "RUNNING"]
            ).exists():
                return Response({"detail": "该产品已有 AI 判断任务执行中"}, status=409)
            reviewed = GovernanceAIReview.objects.values_list("quality_id", flat=True)
            rows = ReviewQuality.objects.filter(review__product=product, eligible_for_ai=True)
            if source_id is not None:
                rows = rows.filter(review__source_id=source_id)
            remaining = rows.exclude(pk__in=reviewed)
            scope_total = remaining.count()
            ids = list(remaining.order_by("pk").values_list("pk", flat=True)[:100])
            if not ids:
                return Response({"detail": "没有待 AI 判断的数据", "total": 0}, status=200)
            batch = GovernanceAIBatch.objects.create(
                product=product, source_id=source_id, requested_by_id=user_id,
                automatic=True, quality_ids=ids, total=len(ids), scope_total=scope_total,
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
        return Response({"id": batch.id, "total": batch.scope_total, "automatic": True}, status=202)

    @action(detail=False, methods=["get"], url_path="full-progress")
    def full_progress(self, request: Request) -> Response:
        from django.db.models import Sum

        try:
            root_id = int(request.query_params.get("id", ""))
        except (ValueError, TypeError):
            return Response({"detail": "无效任务编号"}, status=400)
        root = GovernanceAIBatch.objects.filter(pk=root_id, automatic=True, root_batch__isnull=True).first()
        if root is None:
            return Response({"detail": "全量任务不存在"}, status=404)
        batches = GovernanceAIBatch.objects.filter(pk=root.pk) | GovernanceAIBatch.objects.filter(root_batch=root)
        totals = batches.aggregate(processed=Sum("processed"), failed=Sum("failed"),
                                   accepted=Sum("accepted"), rejected=Sum("rejected"),
                                   uncertain=Sum("uncertain"), prompt_tokens=Sum("prompt_tokens"),
                                   completion_tokens=Sum("completion_tokens"))
        active = batches.filter(status__in=["PENDING", "RUNNING"]).exists()
        status_label = "STOPPED" if root.stop_requested and not active else ("RUNNING" if active else "COMPLETED")
        return Response({"id": root.pk, "status": status_label, "total": root.scope_total,
                         "remaining": max(0, root.scope_total - (totals["processed"] or 0)),
                         **{key: value or 0 for key, value in totals.items()}})

    @action(detail=False, methods=["post"], url_path="stop-full")
    def stop_full(self, request: Request) -> Response:
        try:
            root_id = int(request.data.get("id", ""))
        except (ValueError, TypeError):
            return Response({"detail": "无效任务编号"}, status=400)
        with transaction.atomic():
            root = GovernanceAIBatch.objects.select_for_update().filter(
                pk=root_id, automatic=True, root_batch__isnull=True
            ).first()
            if root is None:
                return Response({"detail": "全量任务不存在"}, status=404)
            root.stop_requested = True
            root.save(update_fields=["stop_requested", "updated_at"])
        return Response({"id": root.pk, "stop_requested": True})

    @action(detail=False, methods=["post"])
    def confirm(self, request: Request) -> Response:
        class Parameters(serializers.Serializer):
            review_id = serializers.IntegerField(min_value=1)
            eligible = serializers.BooleanField()
            reason = serializers.CharField(min_length=2, max_length=500)

        params = Parameters(data=request.data)
        params.is_valid(raise_exception=True)
        data = params.validated_data
        user_id = request.user.pk
        if user_id is None:
            return Response({"detail": "用户身份无效"}, status=403)
        with transaction.atomic():
            record = (
                GovernanceAIReview.objects.select_for_update()
                .filter(quality__review_id=data["review_id"], status="REVIEW_REQUIRED", human_reviewed_at__isnull=True)
                .order_by("-id")
                .first()
            )
            if record is None:
                return Response({"detail": "没有待确认的 AI 复核记录"}, status=409)
            apply_manual_override(data["review_id"], eligible=data["eligible"], reason=data["reason"])
            record.human_decision = data["eligible"]
            record.human_reason = data["reason"]
            record.human_reviewer_id = user_id
            record.human_reviewed_at = timezone.now()
            record.save(
                update_fields=["human_decision", "human_reason", "human_reviewer", "human_reviewed_at", "updated_at"]
            )
        return Response({"id": record.id, "review_id": data["review_id"], "confirmed": True})

    @action(detail=False, methods=["post"], url_path="retry-failed")
    def retry_failed(self, request: Request) -> Response:
        try:
            batch_id = int(str(request.data.get("batch_id", "")))
        except (TypeError, ValueError):
            return Response({"detail": "无效任务编号"}, status=400)
        user_id = request.user.pk
        if user_id is None:
            return Response({"detail": "用户身份无效"}, status=403)
        with transaction.atomic():
            old = GovernanceAIBatch.objects.select_for_update().filter(pk=batch_id, requested_by_id=user_id).first()
            if old is None:
                return Response({"detail": "任务不存在"}, status=404)
            if old.status not in ("FAILED", "PARTIAL"):
                return Response({"detail": "任务当前不可重试"}, status=409)
            ids = list(dict.fromkeys(old.failure_ids or (old.quality_ids if old.processed == 0 else [])))
            if not ids:
                return Response({"detail": "没有可重试的数据"}, status=409)
            new = GovernanceAIBatch.objects.create(
                product=old.product, requested_by_id=user_id, quality_ids=ids, total=len(ids)
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
    def history(self, request: Request) -> Response:
        items = GovernanceAIBatch.objects.filter(requested_by_id=request.user.pk)
        if product_id := request.query_params.get("product_id"):
            items = items.filter(product_id=int(product_id))
        if source_id := request.query_params.get("source_id"):
            items = items.filter(source_id=int(source_id))
        paginator = GovernancePagination()
        page = paginator.paginate_queryset(items, request)
        data = [
            {
                "id": item.id,
                "product_id": item.product_id,
                "source_id": item.source_id,
                "automatic": item.automatic,
                "status": item.status,
                "total": item.total,
                "processed": item.processed,
                "succeeded": item.succeeded,
                "accepted": item.accepted,
                "rejected": item.rejected,
                "uncertain": item.uncertain,
                "review_required": item.review_required,
                "failed": item.failed,
                "prompt_tokens": item.prompt_tokens,
                "completion_tokens": item.completion_tokens,
                "error_code": item.error_code,
                "created_at": item.created_at,
            }
            for item in (page or [])
        ]
        return paginator.get_paginated_response(data)

    @action(detail=False, methods=["get"])
    def results(self, request: Request) -> Response:
        try:
            product_id = int(request.query_params["product_id"])
        except (KeyError, ValueError):
            return Response({"detail": "请选择产品"}, status=400)
        rows = (
            GovernanceAIReview.objects.filter(quality__review__product_id=product_id)
            .select_related("quality")
            .order_by("-id")
        )
        if source_id := request.query_params.get("source_id"):
            rows = rows.filter(quality__review__source_id=int(source_id))
        paginator = GovernancePagination()
        page = paginator.paginate_queryset(rows, request)
        data = [
            {
                "id": item.id,
                "review_id": item.quality.review_id,
                "status": item.status,
                "rule_eligible": item.rule_eligible,
                "ai_eligible": item.ai_eligible,
                "confidence": item.confidence,
                "reason": item.reason,
                "evidence": item.evidence,
                "model": item.model_name,
                "error_code": item.error_code,
                "attempt_count": item.attempt_count,
                "prompt_tokens": item.prompt_tokens,
                "completion_tokens": item.completion_tokens,
                "human_decision": item.human_decision,
                "human_reviewed_at": item.human_reviewed_at,
            }
            for item in (page or [])
        ]
        return paginator.get_paginated_response(data)
