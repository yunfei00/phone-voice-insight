from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from django.conf import settings
from django.db import connection
from django.db.models import Q, QuerySet
from django.utils import timezone
from pgvector.django import CosineDistance  # type: ignore[import-untyped]

from apps.assistant.embeddings import EmbeddingError, embed_text
from apps.assistant.models import RagDocument, RagIndexStatus
from apps.reviews.models import RecordType, ReviewRecord
from apps.reviews.services.thread_tree import replies_for_thread

_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class RetrievalResult:
    review_id: int
    title: str
    summary: str
    source_url: str
    product_id: int
    product_name: str
    source_id: int
    source_name: str
    published_at: Any
    match_reason: str
    score: float


def clean_text(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = math.sqrt(sum(item * item for item in left)) * math.sqrt(sum(item * item for item in right))
    return numerator / denominator if denominator else 0.0


def build_document_text(thread: ReviewRecord) -> str:
    parts = [clean_text(thread.title), clean_text(thread.content)]
    reply_budget = 10_000
    for reply in replies_for_thread(thread):
        content = clean_text(reply.content)
        if not content:
            continue
        excerpt = content[:800]
        if len(excerpt) > reply_budget:
            excerpt = excerpt[:reply_budget]
        parts.append(excerpt)
        reply_budget -= len(excerpt)
        if reply_budget <= 0:
            break
    return "\n".join(part for part in parts if part)[:16_000]


def index_thread(thread: ReviewRecord) -> RagDocument:
    if thread.record_type != RecordType.THREAD:
        raise ValueError("RAG 只索引帖子主记录")
    text = build_document_text(thread)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    existing = RagDocument.objects.filter(review=thread).first()
    if (
        existing
        and existing.content_hash == content_hash
        and existing.status
        in {
            RagIndexStatus.INDEXED,
            RagIndexStatus.KEYWORD_ONLY,
        }
    ):
        return existing
    defaults: dict[str, Any] = {
        "product": thread.product,
        "source": thread.source,
        "title": clean_text(thread.title),
        "cleaned_text": text,
        "summary": clean_text(thread.content)[:800],
        "content_hash": content_hash,
        "attempts": (existing.attempts if existing else 0) + 1,
        "last_error": "",
    }
    try:
        embedded = embed_text(text)
        if embedded is None:
            defaults.update(
                embedding=None,
                embedding_provider="",
                embedding_model="",
                status=RagIndexStatus.KEYWORD_ONLY,
                indexed_at=timezone.now(),
            )
        else:
            defaults.update(
                embedding=embedded.vector,
                embedding_provider=embedded.provider,
                embedding_model=embedded.model,
                status=RagIndexStatus.INDEXED,
                indexed_at=timezone.now(),
            )
    except EmbeddingError as exc:
        defaults.update(
            embedding=None,
            embedding_provider=settings.RAG_EMBEDDING_PROVIDER,
            embedding_model=settings.RAG_EMBEDDING_MODEL,
            status=RagIndexStatus.FAILED,
            last_error=str(exc)[:500],
            indexed_at=None,
        )
    document, _ = RagDocument.objects.update_or_create(review=thread, defaults=defaults)
    return document


def resolve_thread(record: ReviewRecord) -> ReviewRecord | None:
    if record.record_type == RecordType.THREAD:
        return record
    thread_id = str(record.raw_data.get("thread_id") or "")
    if thread_id:
        thread = ReviewRecord.objects.filter(
            source=record.source,
            product=record.product,
            record_type=RecordType.THREAD,
            raw_data__thread_id=thread_id,
        ).first()
        if thread:
            return thread
    parent = record.parent_external_id
    for _ in range(30):
        if not parent:
            return None
        ancestor = ReviewRecord.objects.filter(source=record.source, external_id=parent).first()
        if ancestor is None:
            return None
        if ancestor.record_type == RecordType.THREAD:
            return ancestor
        parent = ancestor.parent_external_id
    return None


def _scoped_documents(
    *,
    product_id: int | None,
    source_id: int | None,
    start_date: date | None,
    end_date: date | None,
    tags: list[str] | None,
) -> QuerySet[RagDocument]:
    queryset = RagDocument.objects.select_related("review", "product", "source").filter(
        status__in=(RagIndexStatus.INDEXED, RagIndexStatus.KEYWORD_ONLY)
    )
    if product_id:
        queryset = queryset.filter(product_id=product_id)
    if source_id:
        queryset = queryset.filter(source_id=source_id)
    if start_date:
        queryset = queryset.filter(review__published_at__date__gte=start_date)
    if end_date:
        queryset = queryset.filter(review__published_at__date__lte=end_date)
    if tags:
        queryset = queryset.filter(
            Q(review__structured_analyses__aspects__aspect_code__in=tags)
            | Q(review__structured_analyses__aspects__topic_code__in=tags)
        ).distinct()
    return queryset


def hybrid_search(
    query: str,
    *,
    product_id: int | None = None,
    source_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    tags: list[str] | None = None,
    limit: int = 10,
) -> tuple[list[RetrievalResult], dict[str, Any]]:
    query = clean_text(query)
    limit = min(max(limit, 1), settings.RAG_RETRIEVAL_LIMIT)
    queryset = _scoped_documents(
        product_id=product_id,
        source_id=source_id,
        start_date=start_date,
        end_date=end_date,
        tags=tags,
    )
    candidates: dict[int, tuple[RagDocument, float, set[str]]] = {}
    for document in queryset.filter(Q(title__icontains=query) | Q(cleaned_text__icontains=query))[: limit * 4]:
        title_match = query.casefold() in document.title.casefold()
        score = 1.0 if title_match else 0.72
        candidates[document.id] = (document, score, {"标题关键词" if title_match else "正文或回复关键词"})
    vector_status = "未启用"
    try:
        embedded = embed_text(query)
    except EmbeddingError:
        embedded = None
        vector_status = "服务异常, 已降级为关键词检索"
    if embedded is not None:
        vector_status = "已启用"
        if connection.vendor == "postgresql":
            vector_rows = (
                queryset.filter(embedding__isnull=False)
                .annotate(distance=CosineDistance("embedding", embedded.vector))
                .order_by("distance")[: limit * 4]
            )
            for document in vector_rows:
                vector_score = max(0.0, 1.0 - float(document.distance))
                previous = candidates.get(document.id)
                if previous:
                    candidates[document.id] = (
                        document,
                        round(previous[1] * 0.45 + vector_score * 0.55, 6),
                        previous[2] | {"语义相似"},
                    )
                else:
                    candidates[document.id] = (document, vector_score * 0.8, {"语义相似"})
        else:
            vector_status = "测试数据库使用受限余弦回退"
            for document in queryset.filter(embedding__isnull=False)[:500]:
                raw_vector = document.embedding
                document_vector = [float(item) for item in raw_vector] if raw_vector is not None else []
                if len(document_vector) != len(embedded.vector):
                    continue
                vector_score = max(0.0, _cosine_similarity(document_vector, embedded.vector))
                previous = candidates.get(document.id)
                if previous:
                    candidates[document.id] = (
                        document,
                        round(previous[1] * 0.45 + vector_score * 0.55, 6),
                        previous[2] | {"语义相似"},
                    )
                else:
                    candidates[document.id] = (document, vector_score * 0.8, {"语义相似"})
    ordered = sorted(candidates.values(), key=lambda item: (-item[1], item[0].id))[:limit]
    rows = [
        RetrievalResult(
            review_id=item.review_id,
            title=item.title or "无标题帖子",
            summary=item.summary,
            source_url=item.review.source_url,
            product_id=item.product_id,
            product_name=item.product.name,
            source_id=item.source_id,
            source_name=item.source.name,
            published_at=item.review.published_at,
            match_reason=" + ".join(sorted(reasons)),
            score=round(score, 4),
        )
        for item, score, reasons in ordered
    ]
    return rows, {"vector_status": vector_status, "candidate_count": len(candidates), "query": query}
