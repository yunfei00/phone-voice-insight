from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.products.models import Product
from apps.reviews.models import AuthorRole, RecordType, ReviewRecord
from apps.reviews.services.thread_tree import parse_human_count
from apps.sources.models import DataSource, SourceTarget

pytestmark = pytest.mark.django_db


def make_record(
    *,
    source_target: SourceTarget,
    product: Product,
    external_id: str,
    record_type: str,
    content: str,
    published_at: Any,
    parent_external_id: str = "",
    title: str = "",
    raw_data: dict[str, object] | None = None,
    is_official: bool = False,
) -> ReviewRecord:
    return ReviewRecord.objects.create(
        source=source_target.source,
        source_target=source_target,
        product=product,
        external_id=external_id,
        parent_external_id=parent_external_id,
        record_type=record_type,
        title=title,
        content=content,
        published_at=published_at,
        author_role=AuthorRole.OFFICIAL if is_official else AuthorRole.USER,
        is_official=is_official,
        source_url=f"https://example.com/{external_id}",
        content_hash=f"hash-{external_id}",
        raw_data=raw_data or {},
        collected_at=timezone.now(),
    )


def make_thread(
    source_target: SourceTarget,
    product: Product,
    *,
    thread_id: str,
    published_at: Any,
    title: str = "普通帖子",
    content: str = "整体还不错",
    reply_count: object = "0",
    view_count: object = "0",
    like_count: object = "0",
) -> ReviewRecord:
    return make_record(
        source_target=source_target,
        product=product,
        external_id=f"thread:{thread_id}",
        record_type=RecordType.THREAD,
        title=title,
        content=content,
        published_at=published_at,
        raw_data={
            "thread_id": thread_id,
            "reply_count": reply_count,
            "view_count": view_count,
            "like_count": like_count,
        },
    )


def make_reply(
    source_target: SourceTarget,
    product: Product,
    *,
    thread_id: str,
    external_id: str,
    parent_external_id: str,
    content: str,
    published_at: Any,
    official: bool = False,
) -> ReviewRecord:
    return make_record(
        source_target=source_target,
        product=product,
        external_id=external_id,
        parent_external_id=parent_external_id,
        record_type=RecordType.OFFICIAL_REPLY if official else RecordType.REPLY,
        content=content,
        published_at=published_at,
        raw_data={"thread_id": thread_id},
        is_official=official,
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("123", 123), ("1.2万", 12000), ("3万", 30000), ("3万+", 30000), ("", None), ("评论", None)],
)
def test_parse_human_count(raw: object, expected: int | None) -> None:
    assert parse_human_count(raw) == expected


def test_thread_detail_builds_nested_tree_and_preserves_orphan(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
) -> None:
    now = timezone.now()
    thread = make_thread(source_target, product, thread_id="100", published_at=now)
    make_reply(
        source_target,
        product,
        thread_id="100",
        external_id="honor_post:101",
        parent_external_id="thread:100",
        content="一级回复",
        published_at=now + timedelta(hours=1),
    )
    make_reply(
        source_target,
        product,
        thread_id="100",
        external_id="honor_comment:102",
        parent_external_id="honor_post:101",
        content="楼中楼回复",
        published_at=now + timedelta(hours=2),
    )
    make_reply(
        source_target,
        product,
        thread_id="100",
        external_id="honor_post:103",
        parent_external_id="thread:100",
        content="官方回复",
        published_at=now + timedelta(hours=3),
        official=True,
    )
    make_reply(
        source_target,
        product,
        thread_id="100",
        external_id="honor_comment:104",
        parent_external_id="missing:999",
        content="孤立回复",
        published_at=now + timedelta(hours=4),
    )

    response = api_client.get(f"/api/v1/thread-trees/{thread.id}/")

    assert response.status_code == 200
    roots = response.json()["replies"]
    first = next(item for item in roots if item["external_id"] == "honor_post:101")
    assert first["children"][0]["external_id"] == "honor_comment:102"
    official = next(item for item in roots if item["external_id"] == "honor_post:103")
    assert official["record_type"] == "OFFICIAL_REPLY" and official["is_official"] is True
    orphan = next(item for item in roots if item["external_id"] == "honor_comment:104")
    assert orphan["unresolved_parent"] is True
    assert sum(1 + len(item["children"]) for item in roots) == 4


def test_search_matches_reply_and_reports_hit_count(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
) -> None:
    now = timezone.now()
    thread = make_thread(source_target, product, thread_id="200", published_at=now)
    make_reply(
        source_target,
        product,
        thread_id="200",
        external_id="honor_post:201",
        parent_external_id="thread:200",
        content="我这里地库信号不太好",
        published_at=now + timedelta(hours=1),
    )

    response = api_client.get("/api/v1/thread-trees/", {"search": "信号"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [thread.id]
    assert response.json()["results"][0]["thread_match"] is False
    assert response.json()["results"][0]["reply_match_count"] == 1
    assert response.json()["matched_reply_count"] == 1


def test_latest_reply_and_collected_count(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
) -> None:
    now = timezone.now()
    thread = make_thread(
        source_target,
        product,
        thread_id="300",
        published_at=now,
        reply_count="8",
        view_count="1.2万",
        like_count="3万+",
    )
    for index, hours in enumerate((1, 2, 6), start=1):
        make_reply(
            source_target,
            product,
            thread_id="300",
            external_id=f"honor_post:30{index}",
            parent_external_id="thread:300",
            content=f"回复{index}",
            published_at=now + timedelta(hours=hours),
        )

    response = api_client.get("/api/v1/thread-trees/")
    item = next(value for value in response.json()["results"] if value["id"] == thread.id)

    assert item["latest_reply_at"] == (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    assert item["reply_count"] == 8
    assert item["collected_reply_count"] == 3
    assert item["view_count"] == 12000
    assert item["like_count"] == 30000


def test_thread_ordering(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
) -> None:
    now = timezone.now()
    old_active = make_thread(
        source_target,
        product,
        thread_id="401",
        published_at=now - timedelta(days=5),
        reply_count="99",
        view_count="100",
    )
    newest = make_thread(
        source_target,
        product,
        thread_id="402",
        published_at=now,
        reply_count="2",
        view_count="200",
    )
    most_viewed = make_thread(
        source_target,
        product,
        thread_id="403",
        published_at=now - timedelta(days=2),
        reply_count="10",
        view_count="2万",
    )
    make_reply(
        source_target,
        product,
        thread_id="401",
        external_id="honor_post:404",
        parent_external_id="thread:401",
        content="今天仍在讨论",
        published_at=now + timedelta(hours=1),
    )

    def first(ordering: str) -> int:
        response = api_client.get("/api/v1/thread-trees/", {"ordering": ordering})
        assert response.status_code == 200
        return response.json()["results"][0]["id"]

    assert first("latest_reply") == old_active.id
    assert first("latest_thread") == newest.id
    assert first("reply_count") == old_active.id
    assert first("view_count") == most_viewed.id


def test_published_and_activity_time_filters(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
) -> None:
    now = timezone.now()
    old_active = make_thread(
        source_target,
        product,
        thread_id="501",
        published_at=now - timedelta(days=20),
    )
    recent = make_thread(
        source_target,
        product,
        thread_id="502",
        published_at=now - timedelta(days=2),
    )
    make_reply(
        source_target,
        product,
        thread_id="501",
        external_id="honor_post:503",
        parent_external_id="thread:501",
        content="旧帖新回复",
        published_at=now - timedelta(hours=1),
    )
    after = (now - timedelta(days=7)).isoformat()
    before = (now + timedelta(days=1)).isoformat()

    published = api_client.get(
        "/api/v1/thread-trees/",
        {"published_at_after": after, "published_at_before": before},
    )
    active = api_client.get(
        "/api/v1/thread-trees/",
        {"activity_at_after": after, "activity_at_before": before},
    )

    assert [item["id"] for item in published.json()["results"]] == [recent.id]
    assert {item["id"] for item in active.json()["results"]} == {old_active.id, recent.id}


def test_product_and_source_filters(
    api_client: APIClient,
    source_target: SourceTarget,
    product: Product,
    source: DataSource,
) -> None:
    thread = make_thread(source_target, product, thread_id="600", published_at=timezone.now())

    by_id = api_client.get("/api/v1/thread-trees/", {"product": product.id, "source": source.id})
    by_code = api_client.get("/api/v1/thread-trees/", {"source": source.code})

    assert [item["id"] for item in by_id.json()["results"]] == [thread.id]
    assert [item["id"] for item in by_code.json()["results"]] == [thread.id]
