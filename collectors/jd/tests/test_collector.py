from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from collectors.base import CollectionCheckpoint, CollectorError, CollectorTarget, RawPage
from collectors.jd.client import JDClient
from collectors.jd.collector import JDCollector

FIXTURES = Path(__file__).parent / "fixtures"


def valid_target(*, target_url: str = "https://item.jd.com/100310496358.html") -> CollectorTarget:
    return CollectorTarget(
        source_code="JD",
        product_code="HONOR_POWER2",
        target_url=target_url,
        external_id="jd:100310496358",
        config={
            "product_id": "100310496358",
            "request_interval_seconds": 4,
            "max_pages": 3,
            "page_size": 10,
        },
    )


def test_valid_target_and_product_fixture() -> None:
    collector = JDCollector()
    assert collector.validate_target(valid_target()).is_valid
    raw_page = RawPage(
        content=(FIXTURES / "product_page.html").read_text(encoding="utf-8"),
        fetched_at=datetime.now(UTC),
        checkpoint=CollectionCheckpoint(),
        metadata={"page_kind": "product", "product_id": "100310496358"},
    )
    assert collector.parse_records(raw_page)[0].payload["shop_name"] == "荣耀京东自营旗舰店"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/100310496358.html",
        "https://127.0.0.1/100310496358.html",
        "https://localhost/100310496358.html",
        "http://item.jd.com/100310496358.html",
        "https://user@item.jd.com/100310496358.html",
        "https://item.jd.com:8443/100310496358.html",
    ],
)
def test_rejects_unsafe_target_urls(url: str) -> None:
    assert not JDCollector().validate_target(valid_target(target_url=url)).is_valid


def test_client_rejects_redirect_before_following() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://passport.jd.com/new/login.aspx"})

    client = JDClient(transport=httpx.MockTransport(handler))
    with pytest.raises(CollectorError) as exc_info:
        client.get_product_page(
            product_url="https://item.jd.com/100310496358.html",
            request_interval_seconds=4,
        )
    assert exc_info.value.code == "UNEXPECTED_REDIRECT"
    assert requested == ["https://item.jd.com/100310496358.html"]


def test_comments_endpoint_fails_closed_until_verified() -> None:
    with pytest.raises(CollectorError) as exc_info:
        JDClient().get_comments_page(
            product_url="https://item.jd.com/100310496358.html",
            request_interval_seconds=4,
        )
    assert exc_info.value.code == "ENDPOINT_NOT_VERIFIED"
