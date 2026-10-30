from __future__ import annotations

# ruff: noqa: RUF001
import hashlib
import json
import statistics
import time
import uuid
from datetime import timedelta
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection, transaction
from django.db.models import Count, Q
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile, UserRole
from apps.analysis.models import AnalysisRun, OpinionAspect, StructuredAnalysis, StructuredRunStatus
from apps.products.models import Brand, Product
from apps.reviews.models import AuthorRole, GovernanceAIReview, RecordType, ReviewQuality, ReviewRecord
from apps.reviews.services.final_corpus import final_corpus_reviews
from apps.sources.models import DataSource, SourceTarget, SourceType, TargetType


class Command(BaseCommand):
    help = "在隔离 PostgreSQL 中构造观点数据并测量结构化聚合接口；全部数据在事务结束时回滚。"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--confirm-isolated", action="store_true")
        parser.add_argument("--sizes", nargs="+", type=int, default=(1_000, 10_000, 50_000))
        parser.add_argument("--contents", type=int, default=1_000)

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        if not options["confirm_isolated"]:
            raise CommandError("仅允许在隔离数据库执行；请显式传入 --confirm-isolated。")
        if connection.vendor != "postgresql":
            raise CommandError("性能基准必须在 PostgreSQL 中执行。")
        sizes = sorted(set(options["sizes"]))
        if not sizes or sizes[0] <= 0 or sizes[-1] > 100_000:
            raise CommandError("观点规模必须在 1 到 100000 之间。")
        content_count = options["contents"]
        if content_count <= 0 or content_count > sizes[0]:
            raise CommandError("contents 必须大于 0 且不能超过最小观点规模。")

        with transaction.atomic():
            context = self._seed_contents(content_count)
            aspect_count = 0
            last_queries: list[dict[str, str]] = []
            for size in sizes:
                self._append_aspects(context["analyses"], aspect_count, size)
                aspect_count = size
                result, last_queries = self._measure(context["user"], context["product"].pk)
                result["opinion_scale"] = size
                self.stdout.write(f"BENCHMARK {json.dumps(result, ensure_ascii=False)}")
            self._write_slowest(last_queries)
            self._write_explain(context["product"])
            transaction.set_rollback(True)

    def _seed_contents(self, content_count: int) -> dict[str, Any]:
        marker = uuid.uuid4().hex[:12]
        now = timezone.now()
        user = get_user_model().objects.create_user(username=f"perf-{marker}")
        UserProfile.objects.create(user=user, role=UserRole.ADMIN)
        brand = Brand.objects.create(name=f"性能品牌-{marker}", code=f"PERF_{marker}")
        product = Product.objects.create(
            brand=brand,
            name=f"性能产品-{marker}",
            normalized_name=f"PERF_PRODUCT_{marker}",
            series="性能测试",
        )
        source = DataSource.objects.create(
            code=f"PERF_SOURCE_{marker}",
            name=f"性能来源-{marker}",
            source_type=SourceType.COMMUNITY,
        )
        target = SourceTarget.objects.create(
            source=source,
            product=product,
            name=f"性能入口-{marker}",
            target_type=TargetType.COMMUNITY,
        )
        reviews = [
            ReviewRecord(
                product=product,
                source=source,
                source_target=target,
                external_id=f"perf-{marker}-{index}",
                record_type=RecordType.REPLY,
                title="性能测试反馈",
                content="地下车库信号不稳定，系统偶尔发热。",
                content_hash=hashlib.sha256(f"{marker}-{index}".encode()).hexdigest(),
                author_role=AuthorRole.USER,
                collected_at=now,
                published_at=now - timedelta(days=index % 35),
            )
            for index in range(content_count)
        ]
        ReviewRecord.objects.bulk_create(reviews, batch_size=2_000)
        qualities = [
            ReviewQuality(
                review=review,
                has_meaningful_text=True,
                is_product_related=True,
                has_product_experience_signal=True,
                eligible_for_ai=True,
                is_official_content=False,
                processor_version="performance-v1",
                processed_at=now,
            )
            for review in reviews
        ]
        ReviewQuality.objects.bulk_create(qualities, batch_size=2_000)
        GovernanceAIReview.objects.bulk_create(
            [
                GovernanceAIReview(
                    quality=quality,
                    status=GovernanceAIReview.Status.ACCEPTED,
                    rule_eligible=True,
                    ai_eligible=True,
                    input_hash=hashlib.sha256(f"governance-{marker}-{index}".encode()).hexdigest(),
                )
                for index, quality in enumerate(qualities)
            ],
            batch_size=2_000,
        )
        runs = [
            AnalysisRun(
                content=review,
                status=StructuredRunStatus.SUCCEEDED,
                provider="performance",
                model="fixture",
                input_hash=hashlib.sha256(f"input-{marker}-{index}".encode()).hexdigest(),
                configuration_hash=hashlib.sha256(f"config-{marker}".encode()).hexdigest(),
                is_current=True,
                completed_at=now,
            )
            for index, review in enumerate(reviews)
        ]
        AnalysisRun.objects.bulk_create(runs, batch_size=2_000)
        analyses = [
            StructuredAnalysis(
                run=run,
                content=review,
                overall_sentiment="NEGATIVE",
                language="zh-CN",
                content_type="COMMUNITY_REPLY",
                relevance="RELEVANT",
                summary="性能测试",
                schema_valid=True,
                review_required=False,
            )
            for run, review in zip(runs, reviews, strict=True)
        ]
        StructuredAnalysis.objects.bulk_create(analyses, batch_size=2_000)
        return {"user": user, "product": product, "analyses": analyses}

    def _append_aspects(
        self,
        analyses: list[StructuredAnalysis],
        start: int,
        end: int,
    ) -> None:
        batch: list[OpinionAspect] = []
        for index in range(start, end):
            batch.append(
                OpinionAspect(
                    analysis=analyses[index % len(analyses)],
                    business_domains=["NET"],
                    aspect_code="NET",
                    topic_code=f"NET.PERF_{index % 100:03d}",
                    sentiment=("NEGATIVE", "NEUTRAL", "POSITIVE")[index % 3],
                    intent="COMPLAINT" if index % 4 else "SUGGESTION",
                    issue_type="RELIABILITY",
                    severity=("LOW", "MEDIUM", "HIGH")[index % 3],
                    scenario="性能测试场景",
                    trigger=None,
                    phenomenon="信号不稳定",
                    target_product=None,
                    compared_products=["对比产品"] if index % 10 == 0 else [],
                    relation_type="SELF",
                    evidence_text="信号不稳定",
                    evidence_start=4,
                    evidence_end=9,
                    confidence=0.9,
                    review_required=False,
                )
            )
            if len(batch) == 2_000:
                OpinionAspect.objects.bulk_create(batch, batch_size=2_000)
                batch.clear()
        if batch:
            OpinionAspect.objects.bulk_create(batch, batch_size=2_000)

    def _measure(self, user: Any, product_id: int) -> tuple[dict[str, Any], list[dict[str, str]]]:
        client = APIClient()
        client.force_authenticate(user=user)
        samples: list[tuple[float, float, int]] = []
        captured_queries: list[dict[str, str]] = []
        status_code = 0
        for _ in range(3):
            with CaptureQueriesContext(connection) as captured:
                started = time.perf_counter()
                response = client.get(
                    f"/api/v1/structured-analyses/aggregates/?product={product_id}",
                    HTTP_HOST="localhost",
                )
                elapsed = time.perf_counter() - started
            status_code = response.status_code
            captured_queries = list(captured.captured_queries)
            database_seconds = sum(float(item.get("time", 0) or 0) for item in captured_queries)
            samples.append((elapsed, database_seconds, len(captured_queries)))
        return (
            {
                "status": status_code,
                "sql_count": int(statistics.median(item[2] for item in samples)),
                "database_seconds_median": round(statistics.median(item[1] for item in samples), 6),
                "response_seconds_median": round(statistics.median(item[0] for item in samples), 6),
                "response_seconds_max": round(max(item[0] for item in samples), 6),
            },
            captured_queries,
        )

    def _write_slowest(self, queries: list[dict[str, str]]) -> None:
        for index, item in enumerate(
            sorted(queries, key=lambda row: float(row.get("time", 0) or 0), reverse=True)[:10],
            start=1,
        ):
            payload = {
                "rank": index,
                "seconds": float(item.get("time", 0) or 0),
                "sql": item.get("sql", "").replace("\n", " ")[:1_500],
            }
            self.stdout.write(f"SLOW_SQL {json.dumps(payload, ensure_ascii=False)}")

    def _write_explain(self, product: Product) -> None:
        now = timezone.now()
        recent_start = now - timedelta(days=7)
        baseline_start = recent_start - timedelta(days=28)
        aspects = OpinionAspect.objects.filter(
            analysis__content__product=product,
            analysis__run__is_current=True,
            analysis__run__status=StructuredRunStatus.SUCCEEDED,
            analysis__schema_valid=True,
            analysis__review_required=False,
            analysis__content_id__in=final_corpus_reviews().values("pk"),
        )
        legacy_query = aspects.filter(
            topic_code="NET.PERF_000",
            analysis__content__published_at__gte=recent_start,
        )
        self.stdout.write(
            f"EXPLAIN_LEGACY_TOPIC_COUNT {legacy_query.explain(analyze=True, buffers=True, format='json')}"
        )
        optimized_query = (
            aspects.values("topic_code")
            .annotate(
                recent=Count(
                    "id",
                    filter=Q(analysis__content__published_at__gte=recent_start),
                ),
                baseline=Count(
                    "id",
                    filter=Q(
                        analysis__content__published_at__gte=baseline_start,
                        analysis__content__published_at__lt=recent_start,
                    ),
                ),
            )
            .order_by("topic_code")
        )
        self.stdout.write(
            f"EXPLAIN_OPTIMIZED_WINDOWS {optimized_query.explain(analyze=True, buffers=True, format='json')}"
        )
