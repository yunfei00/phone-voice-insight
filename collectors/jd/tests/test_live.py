import os

import pytest

from collectors.base import CollectionCheckpoint, CollectionRequest, CollectorTarget
from collectors.jd.collector import JDCollector
from collectors.jd.constants import VERIFIED_COMMENT_ENDPOINT, VERIFIED_COMMENT_FIELD_MAP


@pytest.mark.skipif(os.getenv("RUN_JD_LIVE_TESTS") != "1", reason="set RUN_JD_LIVE_TESTS=1 explicitly")
def test_live_product_and_one_comment_page() -> None:
    if VERIFIED_COMMENT_ENDPOINT is None or not VERIFIED_COMMENT_FIELD_MAP:
        pytest.skip("current JD comments endpoint/schema has not passed the live verification gate")
    target = CollectorTarget(
        source_code="JD",
        product_code="HONOR_POWER2",
        target_url="https://item.jd.com/100310496358.html",
        external_id="jd:100310496358",
        config={
            "product_id": "100310496358",
            "request_interval_seconds": 4,
            "max_pages": 1,
            "page_size": 10,
        },
    )
    collector = JDCollector()
    product = collector.fetch_page(
        CollectionRequest(
            target=target,
            checkpoint=CollectionCheckpoint(metadata={"page_kind": "product", "product_id": "100310496358"}),
        )
    )
    assert collector.parse_records(product)[0].external_id == "jd_product:100310496358"
    comments = collector.fetch_page(
        CollectionRequest(
            target=target,
            checkpoint=CollectionCheckpoint(
                page=1,
                metadata={"page_kind": "comments", "product_id": "100310496358", "page_size": 10},
            ),
            limit=10,
        )
    )
    records = collector.parse_records(comments)
    assert any(record.external_id and record.record_type == "REVIEW" for record in records)
