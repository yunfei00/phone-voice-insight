"""Thread-centric querying and reply tree construction."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.db.models import (
    BooleanField,
    Case,
    Count,
    DateTimeField,
    Exists,
    F,
    FloatField,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    TextField,
    Value,
    When,
)
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Greatest, Replace

from apps.reviews.models import RecordType, ReviewRecord

_HUMAN_COUNT_PATTERN = re.compile(r"^(?P<number>\d+(?:\.\d+)?)(?P<unit>万)?\+?$")
_REPLY_TYPES = (RecordType.REPLY, RecordType.OFFICIAL_REPLY)


def parse_human_count(value: object) -> int | None:
    """Parse Honor counters without allowing malformed source text to fail an API."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(round(value), 0)
    normalized = str(value or "").strip().replace(",", "").replace(" ", "")
    if not normalized:
        return None
    match = _HUMAN_COUNT_PATTERN.fullmatch(normalized)
    if not match:
        return None
    number = float(match.group("number"))
    if match.group("unit"):
        number *= 10_000
    return max(round(number), 0)


def _associated_replies() -> QuerySet[ReviewRecord]:
    return (
        ReviewRecord.objects.filter(
            source_id=OuterRef("source_id"),
            product_id=OuterRef("product_id"),
            record_type__in=_REPLY_TYPES,
        )
        .annotate(reply_thread_id=KeyTextTransform("thread_id", "raw_data"))
        .filter(Q(reply_thread_id=OuterRef("thread_id_value")) | Q(parent_external_id=OuterRef("external_id")))
    )


def _count_subquery(queryset: QuerySet[ReviewRecord]) -> Subquery:
    counted = queryset.order_by().values("source_id").annotate(total=Count("id")).values("total")
    return Subquery(counted, output_field=IntegerField())


def _human_count_expression(raw_alias: str) -> Case:
    compact_alias = f"{raw_alias}_compact"
    numeric_alias = f"{raw_alias}_number"
    return Case(
        When(**{f"{compact_alias}__regex": r"^\d+\+?$"}, then=Cast(F(numeric_alias), IntegerField())),
        When(
            **{f"{compact_alias}__regex": r"^\d+(?:\.\d+)?万\+?$"},
            then=Cast(Cast(F(numeric_alias), FloatField()) * Value(10_000), IntegerField()),
        ),
        default=Value(None),
        output_field=IntegerField(),
    )


def annotate_thread_metrics(queryset: QuerySet[ReviewRecord]) -> QuerySet[ReviewRecord]:
    replies = _associated_replies()
    latest_reply = replies.filter(published_at__isnull=False).order_by("-published_at", "-id")
    queryset = queryset.annotate(
        thread_id_value=KeyTextTransform("thread_id", "raw_data"),
        reply_count_raw=KeyTextTransform("reply_count", "raw_data"),
        view_count_raw=KeyTextTransform("view_count", "raw_data"),
        like_count_raw=KeyTextTransform("like_count", "raw_data"),
    )
    for name in ("reply_count", "view_count", "like_count"):
        queryset = queryset.annotate(
            **{
                f"{name}_compact": Replace(
                    Replace(
                        F(f"{name}_raw"),
                        Value(","),
                        Value(""),
                        output_field=TextField(),
                    ),
                    Value(" "),
                    Value(""),
                    output_field=TextField(),
                ),
            }
        ).annotate(
            **{
                f"{name}_number": Replace(
                    Replace(
                        F(f"{name}_compact"),
                        Value("+"),
                        Value(""),
                        output_field=TextField(),
                    ),
                    Value("万"),
                    Value(""),
                    output_field=TextField(),
                )
            }
        )
    queryset = queryset.annotate(
        collected_reply_count=_count_subquery(replies),
        latest_reply_at=Subquery(latest_reply.values("published_at")[:1], output_field=DateTimeField()),
        parsed_reply_count=_human_count_expression("reply_count"),
        parsed_view_count=_human_count_expression("view_count"),
        parsed_like_count=_human_count_expression("like_count"),
    )
    return queryset.annotate(
        activity_at=Case(
            When(latest_reply_at__isnull=True, then=F("published_at")),
            When(published_at__isnull=True, then=F("latest_reply_at")),
            default=Greatest(F("published_at"), F("latest_reply_at")),
            output_field=DateTimeField(),
        )
    )


def filter_thread_search(queryset: QuerySet[ReviewRecord], search: str) -> QuerySet[ReviewRecord]:
    if not search:
        return queryset.annotate(
            thread_match=Value(False, output_field=BooleanField()),
            reply_match_count=Value(0, output_field=IntegerField()),
            reply_match_count_safe=Value(0, output_field=IntegerField()),
        )
    reply_matches = _associated_replies().filter(Q(title__icontains=search) | Q(content__icontains=search))
    thread_match_query = Q(title__icontains=search) | Q(content__icontains=search)
    return (
        queryset.annotate(
            thread_match=Case(
                When(thread_match_query, then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            ),
            reply_match_count=_count_subquery(reply_matches),
            has_reply_match=Exists(reply_matches),
        )
        .filter(thread_match_query | Q(has_reply_match=True))
        .annotate(
            reply_match_count_safe=Case(
                When(reply_match_count__isnull=True, then=Value(0)),
                default=F("reply_match_count"),
                output_field=IntegerField(),
            )
        )
    )


@dataclass(frozen=True)
class ReplyTreeNode:
    record: ReviewRecord
    children: tuple[ReplyTreeNode, ...]
    unresolved_parent: bool = False


def replies_for_thread(thread: ReviewRecord) -> list[ReviewRecord]:
    """Load one thread's replies, with depth-batched fallback for legacy rows."""

    thread_id = str(thread.raw_data.get("thread_id", ""))
    base = ReviewRecord.objects.filter(
        source_id=thread.source_id,
        product_id=thread.product_id,
        record_type__in=_REPLY_TYPES,
    )
    association = Q(parent_external_id=thread.external_id)
    if thread_id:
        association |= Q(raw_data__thread_id=thread_id)
    records = list(base.filter(association).order_by("published_at", "id"))
    known_ids = {record.id for record in records}
    frontier = {str(record.external_id) for record in records if record.external_id}
    for _depth in range(50):
        if not frontier:
            break
        children = list(base.filter(parent_external_id__in=frontier).exclude(id__in=known_ids))
        if not children:
            break
        records.extend(children)
        known_ids.update(record.id for record in children)
        frontier = {str(record.external_id) for record in children if record.external_id}
    return records


def build_reply_tree(thread: ReviewRecord, replies: Iterable[ReviewRecord]) -> list[ReplyTreeNode]:
    records = list(replies)

    def key_for(record: ReviewRecord) -> str:
        return str(record.external_id or f"db:{record.id}")

    by_key = {key_for(record): record for record in records}
    children_by_parent: dict[str, list[ReviewRecord]] = defaultdict(list)
    roots: list[tuple[ReviewRecord, bool]] = []
    thread_key = str(thread.external_id or "")
    for record in records:
        parent_key = str(record.parent_external_id or "")
        if parent_key and parent_key in by_key and parent_key != key_for(record):
            children_by_parent[parent_key].append(record)
        else:
            roots.append((record, bool(parent_key and parent_key != thread_key)))

    visited: set[str] = set()

    def visit(record: ReviewRecord, *, unresolved: bool, path: frozenset[str]) -> ReplyTreeNode:
        key = key_for(record)
        visited.add(key)
        child_nodes: list[ReplyTreeNode] = []
        for child in children_by_parent.get(key, []):
            child_key = key_for(child)
            if child_key in path or child_key in visited:
                continue
            child_nodes.append(visit(child, unresolved=False, path=path | {key}))
        return ReplyTreeNode(record=record, children=tuple(child_nodes), unresolved_parent=unresolved)

    tree = [visit(record, unresolved=unresolved, path=frozenset()) for record, unresolved in roots]
    for record in records:
        if key_for(record) not in visited:
            tree.append(visit(record, unresolved=True, path=frozenset()))
    return tree


def serialize_reply_node(node: ReplyTreeNode) -> dict[str, Any]:
    record = node.record
    return {
        "id": record.id,
        "external_id": record.external_id,
        "parent_external_id": record.parent_external_id,
        "record_type": record.record_type,
        "content": record.content,
        "published_at": record.published_at,
        "ip_location": record.source_region if record.region_evidence == "public_ip_region" else "",
        "profile_region": record.source_region if record.region_evidence == "public_profile_region" else "",
        "author_role": record.author_role,
        "is_official": record.is_official,
        "source_url": record.source_url,
        "unresolved_parent": node.unresolved_parent,
        "children": [serialize_reply_node(child) for child in node.children],
    }


def serialize_thread(thread: ReviewRecord) -> dict[str, Any]:
    return {
        "id": thread.id,
        "external_id": thread.external_id,
        "product": thread.product_id,
        "product_name": thread.product.name,
        "source": thread.source_id,
        "source_name": thread.source.name,
        "title": thread.title,
        "content": thread.content,
        "published_at": thread.published_at,
        "ip_location": thread.source_region if thread.region_evidence == "public_ip_region" else "",
        "profile_region": thread.source_region if thread.region_evidence == "public_profile_region" else "",
        "latest_reply_at": getattr(thread, "latest_reply_at", None),
        "activity_at": getattr(thread, "activity_at", thread.published_at),
        "reply_count": getattr(thread, "parsed_reply_count", parse_human_count(thread.raw_data.get("reply_count"))),
        "collected_reply_count": getattr(thread, "collected_reply_count", None) or 0,
        "view_count": getattr(thread, "parsed_view_count", parse_human_count(thread.raw_data.get("view_count"))),
        "like_count": getattr(thread, "parsed_like_count", parse_human_count(thread.raw_data.get("like_count"))),
        "source_url": thread.source_url,
        "thread_match": bool(getattr(thread, "thread_match", False)),
        "reply_match_count": int(
            getattr(thread, "reply_match_count_safe", getattr(thread, "reply_match_count", 0)) or 0
        ),
    }
