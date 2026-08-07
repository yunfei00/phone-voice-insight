import os
from pathlib import Path

import httpx
import pytest

from collectors.base import CollectionCheckpoint, CollectionRequest, CollectorError, CollectorTarget
from collectors.honor_club import HonorClubCollector
from collectors.honor_club.client import HonorClubClient
from collectors.honor_club.date_parser import parse_honor_datetime
from collectors.honor_club.parser import extract_topic_page_count, parse_thread_page, parse_topic_page
from collectors.honor_club.role_mapper import map_author_role

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_topic_page_extracts_stable_threads_and_pagination() -> None:
    html = fixture("topic_page.html")
    records = parse_topic_page(html, topic_id=595)

    assert [record.payload["thread_id"] for record in records] == ["10001", "10002"]
    assert records[0].payload["thread_url"] == "https://club.honor.com/cn/thread-10001-1-1.html"
    assert records[0].payload["title"] == "荣耀Power2 续航体验"
    assert extract_topic_page_count(html, topic_id=595) == 2


def test_thread_page_extracts_thread_reply_time_and_device() -> None:
    records = parse_thread_page(
        fixture("thread_page.html"),
        thread_id="10001",
        thread_url="https://club.honor.com/cn/thread-10001-1-1.html",
        listing_data={"title": "荣耀Power2 续航体验", "topic_tags": ["#荣耀Power2#"]},
    )

    assert [record.record_type for record in records] == ["THREAD", "REPLY"]
    assert "真实楼主正文" in records[0].payload["content"]
    assert records[0].payload["raw_data"]["device_source"] == "荣耀Power2"
    assert records[1].external_id == "honor_post:20001"
    assert records[1].payload["parent_external_id"] == "thread:10001"
    assert records[1].payload["published_at"].year == 2026


def test_image_only_thread_does_not_use_topic_metadata_as_content() -> None:
    html = """
    <div class="hbtTbox"><h1>Image showcase</h1></div>
    <div class="hbt-artc wapFirstThread">
      <div class="imagebox"><img src="example.jpg"></div>
      <div class="protalTag"><a class="protalTag2">HONOR Power2</a></div>
      <div><p class="ordinary_eye_num">9567 views</p></div>
      <p class="ordinary_last_text"></p>
    </div>
    """

    records = parse_thread_page(
        html,
        thread_id="10005",
        thread_url="https://club.honor.com/cn/thread-10005-1-1.html",
        listing_data={"topic_tags": ["HONOR Power2"]},
    )

    assert records[0].payload["content"] == "Image showcase"
    assert records[0].payload["raw_data"]["image_count"] == 1


def test_official_replies_are_normalized_as_official() -> None:
    collector = HonorClubCollector()
    records = parse_thread_page(
        fixture("thread_with_official_reply.html"),
        thread_id="10003",
        thread_url="https://club.honor.com/cn/thread-10003-1-1.html",
        listing_data={"topic_tags": ["#荣耀Power2#"]},
    )
    normalized = [collector.normalize_record(record) for record in records[1:]]

    assert {record.record_type for record in normalized} == {"OFFICIAL_REPLY"}
    assert all(record.author_role == "OFFICIAL" and record.is_official for record in normalized)
    assert "示例昵称" not in normalized[0].content
    assert normalized[0].content == "建议先检查系统更新。"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("荣耀答答团", "OFFICIAL"),
        ("荣耀俱乐部团队", "OFFICIAL"),
        ("版主", "MODERATOR"),
        ("实习版主", "MODERATOR"),
        ("玩机达人", "EXPERT"),
        ("摄影达人", "EXPERT"),
        ("LV10", "USER"),
        ("未标注", "UNKNOWN"),
    ],
)
def test_role_mapping(text: str, expected: str) -> None:
    assert map_author_role(text) == expected


def test_nested_comment_keeps_post_parent_and_cross_year_time() -> None:
    records = parse_thread_page(
        fixture("thread_with_nested_comment.html"),
        thread_id="10004",
        thread_url="https://club.honor.com/cn/thread-10004-1-1.html",
        listing_data={"topic_tags": ["#荣耀Power2#"]},
    )
    nested = records[-1]

    assert nested.external_id == "honor_comment:31001"
    assert nested.payload["parent_external_id"] == "honor_post:22001"
    assert nested.payload["published_at"].year == 2026
    assert nested.payload["raw_data"]["parent_resolution"] == "post"


def test_invalid_target_is_rejected_without_network() -> None:
    collector = HonorClubCollector()
    for url in (
        "https://example.com/cn/threadtopic-595-1.html",
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://localhost/cn/thread-1-1-1.html",
        "https://127.0.0.1/cn/thread-1-1-1.html",
        "https://club.honor.com:not-a-port/cn/thread-1-1-1.html",
        "https://club.honor.com/cn/thread-1-1-1.html?redirect=https://example.com",
    ):
        result = collector.validate_target(
            CollectorTarget(source_code="HONOR_CLUB", product_code="HONOR_POWER2", target_url=url)
        )
        assert not result.is_valid


def test_unparseable_partial_date_returns_none_without_reference() -> None:
    assert parse_honor_datetime("1-19 19:14:30") is None
    assert parse_honor_datetime("not-a-date") is None


def test_known_mobile_redirect_is_followed_and_canonicalized() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if len(requested_urls) == 1:
            return httpx.Response(
                302,
                headers={"location": "cn/thread-30295048-1-1.html?mobile=2"},
                request=request,
            )
        return httpx.Response(200, headers={"content-type": "text/html"}, text="<html>ok</html>", request=request)

    client = HonorClubClient(transport=httpx.MockTransport(handler))
    response = client.get_html(
        "https://club.honor.com/cn/thread-30295048-1-1.html",
        request_interval_seconds=3,
    )

    assert requested_urls == [
        "https://club.honor.com/cn/thread-30295048-1-1.html",
        "https://club.honor.com/cn/thread-30295048-1-1.html?mobile=2",
    ]
    assert response.url == "https://club.honor.com/cn/thread-30295048-1-1.html"


def test_external_redirect_is_rejected_before_following() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://example.com/blocked"}, request=request)

    client = HonorClubClient(transport=httpx.MockTransport(handler))
    with pytest.raises(CollectorError, match="异常跳转"):
        client.get_html(
            "https://club.honor.com/cn/thread-30295048-1-1.html",
            request_interval_seconds=3,
        )
    assert requested_urls == ["https://club.honor.com/cn/thread-30295048-1-1.html"]


@pytest.mark.skipif(os.getenv("RUN_HONOR_LIVE_TESTS") != "1", reason="live Honor test disabled")
def test_live_smoke_one_topic_and_one_thread() -> None:
    collector = HonorClubCollector()
    target = CollectorTarget(
        source_code="HONOR_CLUB",
        product_code="HONOR_POWER2",
        target_url="https://club.honor.com/cn/threadtopic-595-1.html",
        external_id="topic:595",
        config={"topic_id": 595, "request_interval_seconds": 3},
    )
    topic_page = collector.fetch_page(
        CollectionRequest(
            target=target,
            checkpoint=CollectionCheckpoint(page=1, metadata={"page_kind": "topic", "topic_id": 595}),
            limit=1,
        )
    )
    links = collector.parse_records(topic_page)
    assert links
    link = links[0]
    thread_target = CollectorTarget(
        source_code="HONOR_CLUB",
        product_code="HONOR_POWER2",
        target_url=link.payload["thread_url"],
        config=target.config,
    )
    thread_page = collector.fetch_page(
        CollectionRequest(
            target=thread_target,
            checkpoint=CollectionCheckpoint(
                metadata={"page_kind": "thread", "thread_id": link.payload["thread_id"], "listing_data": link.payload}
            ),
        )
    )
    assert collector.parse_records(thread_page)
