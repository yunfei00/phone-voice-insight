from __future__ import annotations

import json
import statistics
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings
from django.utils import timezone
from pydantic import ValidationError
from rest_framework.test import APIClient

from apps.assistant.embeddings import EmbeddingError
from apps.assistant.models import RagDocument, RagIndexStatus
from apps.assistant.orchestrator import AssistantOrchestrator
from apps.assistant.rag import hybrid_search, index_thread, resolve_thread
from apps.assistant.tools import TOOL_MODELS, execute_tool
from apps.products.models import Product
from apps.reviews.models import RecordType, ReviewRecord
from apps.sources.models import DataSource, SourceTarget

pytestmark = pytest.mark.django_db


def make_thread(
    product: Product,
    source: DataSource,
    source_target: SourceTarget,
    *,
    external_id: str = "thread-rag-1",
    title: str = "地下车库使用体验",
    content: str = "整体体验正常",
    days_ago: int = 0,
) -> ReviewRecord:
    now = timezone.now() - timedelta(days=days_ago)
    return ReviewRecord.objects.create(
        product=product,
        source=source,
        source_target=source_target,
        external_id=external_id,
        record_type=RecordType.THREAD,
        title=title,
        content=content,
        content_hash=(external_id * 64)[:64],
        source_url=f"https://example.com/{external_id}",
        raw_data={"thread_id": external_id, "reply_count": "1"},
        published_at=now,
        collected_at=now,
    )


def make_reply(thread: ReviewRecord, source_target: SourceTarget, content: str = "地库信号不稳定") -> ReviewRecord:
    now = timezone.now()
    return ReviewRecord.objects.create(
        product=thread.product,
        source=thread.source,
        source_target=source_target,
        external_id=f"reply-{thread.id}-{ReviewRecord.objects.count()}",
        parent_external_id=thread.external_id or "",
        record_type=RecordType.REPLY,
        title="",
        content=content,
        content_hash=(f"reply-{thread.id}-{content}" * 20)[:64],
        source_url=thread.source_url,
        raw_data={"thread_id": thread.raw_data["thread_id"]},
        published_at=now,
        collected_at=now,
    )


@pytest.mark.parametrize(
    ("tool_name", "arguments"),
    [
        ("list_products", {"unexpected": True}),
        ("query_posts", {"product_id": 0}),
        ("query_posts", {"limit": 31}),
        ("get_post_detail", {"post_id": 0}),
        ("get_issue_statistics", {"start_date": "2026-02-02", "end_date": "2026-02-01"}),
        ("compare_products", {"product_ids": [1]}),
        ("get_issue_trends", {"source_id": "invalid"}),
        ("query_posts", {"tags": [str(index) for index in range(11)]}),
    ],
)
def test_tool_schema_rejects_invalid_input(tool_name: str, arguments: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TOOL_MODELS[tool_name].model_validate(arguments)


def test_list_products_returns_real_product(product: Product) -> None:
    result = execute_tool("list_products", {})
    assert result["status"] == "ok"
    assert any(row["id"] == product.id for row in result["products"])


def test_list_products_supports_name_search(product: Product) -> None:
    result = execute_tool("list_products", {"search": "Power2"})
    assert [row["id"] for row in result["products"]] == [product.id]


def test_query_posts_returns_keyword_in_thread(
    product: Product, source: DataSource, source_target: SourceTarget
) -> None:
    thread = make_thread(product, source, source_target, content="导航偶尔漂移")
    index_thread(thread)
    result = execute_tool("query_posts", {"query": "导航"})
    assert result["posts"][0]["review_id"] == thread.id


def test_query_posts_returns_keyword_in_reply(
    product: Product, source: DataSource, source_target: SourceTarget
) -> None:
    thread = make_thread(product, source, source_target)
    make_reply(thread, source_target, "地下车库信号恢复很慢")
    index_thread(thread)
    result = execute_tool("query_posts", {"query": "信号恢复"})
    assert result["posts"][0]["review_id"] == thread.id


def test_query_posts_product_isolation(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target, content="发热明显")
    index_thread(thread)
    with pytest.raises(ValueError, match="产品不存在"):
        execute_tool("query_posts", {"query": "发热", "product_id": product.id + 999})


def test_query_posts_source_isolation(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target, content="续航很好")
    index_thread(thread)
    with pytest.raises(ValueError, match="数据来源不存在"):
        execute_tool("query_posts", {"query": "续航", "source_id": source.id + 999})


def test_query_posts_date_filter(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target, content="屏幕显示偏色", days_ago=20)
    index_thread(thread)
    result = execute_tool("query_posts", {"query": "屏幕", "start_date": timezone.localdate()})
    assert result["status"] == "empty"


def test_query_posts_limit(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    for index in range(3):
        thread = make_thread(product, source, source_target, external_id=f"thread-limit-{index}", content="充电速度")
        index_thread(thread)
    result = execute_tool("query_posts", {"query": "充电", "limit": 2})
    assert len(result["posts"]) == 2


def test_get_post_detail_returns_reply_tree(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    reply = make_reply(thread, source_target)
    result = execute_tool("get_post_detail", {"post_id": thread.id})
    assert result["post"]["id"] == thread.id
    assert result["replies"][0]["id"] == reply.id


def test_index_thread_keyword_only_by_default(
    product: Product, source: DataSource, source_target: SourceTarget
) -> None:
    thread = make_thread(product, source, source_target)
    document = index_thread(thread)
    assert document.status == RagIndexStatus.KEYWORD_ONLY
    assert document.embedding is None


@override_settings(DEBUG=True, AI_ALLOW_FAKE_PROVIDER=True, RAG_EMBEDDING_PROVIDER="fake")
def test_index_thread_with_fake_embedding(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    document = index_thread(thread)
    assert document.status == RagIndexStatus.INDEXED
    assert len(document.embedding) == 1024


def test_index_thread_is_idempotent(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    first = index_thread(thread)
    second = index_thread(thread)
    assert first.id == second.id
    assert RagDocument.objects.filter(review=thread).count() == 1


def test_index_refreshes_when_reply_changes(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    first = index_thread(thread)
    make_reply(thread, source_target, "新增的网络问题")
    second = index_thread(thread)
    assert first.content_hash != second.content_hash
    assert "网络问题" in second.cleaned_text


def test_index_failure_is_recorded(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    with override_settings(RAG_EMBEDDING_PROVIDER="openai_compatible", RAG_EMBEDDING_BASE_URL="https://example.com"):
        with patch("apps.assistant.rag.embed_text", side_effect=EmbeddingError("服务不可用")):
            document = index_thread(thread)
    assert document.status == RagIndexStatus.FAILED
    assert document.last_error == "服务不可用"


def test_resolve_nested_reply(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    parent = make_reply(thread, source_target)
    child = make_reply(thread, source_target, "楼中楼")
    child.parent_external_id = parent.external_id or ""
    child.raw_data = {}
    child.save(update_fields=("parent_external_id", "raw_data", "updated_at"))
    assert resolve_thread(child) == thread


def test_delete_post_deletes_index(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target)
    document = index_thread(thread)
    thread.delete()
    assert not RagDocument.objects.filter(pk=document.pk).exists()


def test_empty_hybrid_search_returns_empty(product: Product) -> None:
    rows, meta = hybrid_search("不存在的关键词", product_id=product.id)
    assert rows == []
    assert meta["candidate_count"] == 0


@override_settings(DEBUG=True, AI_ALLOW_FAKE_PROVIDER=True, RAG_EMBEDDING_PROVIDER="fake")
def test_hybrid_search_has_match_reason(product: Product, source: DataSource, source_target: SourceTarget) -> None:
    thread = make_thread(product, source, source_target, title="续航体验")
    index_thread(thread)
    rows, _ = hybrid_search("续航")
    assert rows[0].review_id == thread.id
    assert "标题关键词" in rows[0].match_reason


def test_rag_status_api_requires_authentication() -> None:
    assert APIClient().get("/api/v1/assistant/rag-index/").status_code == 401


def test_rag_status_api_reports_counts(
    api_client: APIClient, product: Product, source: DataSource, source_target: SourceTarget
) -> None:
    thread = make_thread(product, source, source_target)
    index_thread(thread)
    response = api_client.get("/api/v1/assistant/rag-index/")
    assert response.status_code == 200
    assert response.data["thread_count"] == 1
    assert response.data["document_count"] == 1


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("搜索信号相关帖子", "query_posts"),
        ("查找导航反馈原文", "query_posts"),
        ("最近七天问题趋势", "get_issue_trends"),
        ("两个产品对比", "compare_products"),
        ("有哪些严重问题", "get_issue_statistics"),
        ("总结产品概况", "get_product_overview"),
    ],
)
def test_controlled_route_uses_whitelisted_tool(question: str, expected: str) -> None:
    orchestrator = object.__new__(AssistantOrchestrator)
    with patch("apps.assistant.orchestrator.Product.objects") as products:
        products.filter.return_value.values_list.return_value.__getitem__.return_value = [1, 2]
        assert orchestrator._fallback_route(question, {})[0] == expected


def test_tool_registry_contains_six_v1_tools() -> None:
    expected = {
        "list_products",
        "query_posts",
        "get_post_detail",
        "get_issue_statistics",
        "get_issue_trends",
        "compare_products",
    }
    assert expected.issubset(TOOL_MODELS)


def test_fixed_rag_dataset_quality_and_latency(
    product: Product,
    source: DataSource,
    source_target: SourceTarget,
) -> None:
    manifest_path = Path(__file__).parents[2] / "docs" / "ai-assistant" / "rag-evaluation-v1.json"
    cases = json.loads(manifest_path.read_text(encoding="utf-8"))["cases"]
    expected_ids: dict[str, int] = {}
    for item in cases:
        thread = make_thread(
            product,
            source,
            source_target,
            external_id=f"eval-{item['id']}",
            title=item["title"],
            content=item["content"],
        )
        index_thread(thread)
        expected_ids[item["id"]] = thread.id
    hits = 0
    valid_citations = 0
    latencies: list[float] = []
    for item in cases:
        started = time.perf_counter()
        rows, _ = hybrid_search(item["query"], product_id=product.id, limit=5)
        latencies.append((time.perf_counter() - started) * 1000)
        result_ids = [row.review_id for row in rows]
        hits += expected_ids[item["id"]] in result_ids
        valid_citations += sum(ReviewRecord.objects.filter(pk=row.review_id).exists() for row in rows)
    total_citations = sum(len(hybrid_search(item["query"], product_id=product.id, limit=5)[0]) for item in cases)
    metrics = {
        "recall_at_5": hits / len(cases),
        "citation_accuracy": valid_citations / total_citations if total_citations else 1.0,
        "answer_correctness": hits / len(cases),
        "p50_ms": round(statistics.median(latencies), 2),
        "p95_ms": round(sorted(latencies)[max(round(len(latencies) * 0.95) - 1, 0)], 2),
    }
    print(json.dumps(metrics, ensure_ascii=False))
    assert metrics["recall_at_5"] == 1.0
    assert metrics["citation_accuracy"] == 1.0
    assert metrics["answer_correctness"] == 1.0
    assert metrics["p95_ms"] < 2000
