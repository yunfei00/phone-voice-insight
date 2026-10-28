"""AI-assisted governance endpoints."""
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.accounts.permissions import IsAdministrator
from apps.reviews.models import GovernanceAIBatch, GovernanceAIReview

class GovernanceAIViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAdministrator]
    queryset = GovernanceAIBatch.objects.all()

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
