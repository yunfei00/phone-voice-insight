"""Deterministic, coverage-oriented corpus selection."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

from django.db.models import QuerySet

from apps.reviews.models import AnalysisCorpusItem, RecordType

DEFAULT_SAMPLE_SEED = 20260808
CONTEXT_CANDIDATE_MARKERS = ("我也是", "确实", "同感", "我的也", "也这样", "也是这样", "一样")
POSITIVE_MARKERS = ("很好", "不错", "流畅", "满意", "给力", "强")
NEGATIVE_MARKERS = ("差", "掉电", "耗电", "发热", "热", "烫", "卡", "断", "问题", "慢", "模糊")
ASPECT_MARKER_GROUPS = (
    ("续航", "掉电", "耗电", "电池", "待机"),
    ("充电", "快充"),
    ("发热", "热", "烫"),
    ("信号", "网络", "断流", "Wi-Fi", "5G", "4G", "定位"),
    ("掉帧", "帧率", "性能", "游戏"),
    ("流畅", "卡顿", "滑动", "动画"),
    ("闪退", "死机", "重启", "Bug", "通知"),
    ("屏幕", "显示", "亮度", "护眼"),
    ("拍照", "相机", "成像", "照片", "录像"),
    ("太重", "偏重", "重量", "手感"),
    ("做工", "缝隙", "按键", "材质"),
    ("扬声器", "听筒", "麦克风", "音质", "通话"),
    ("耐用", "抗摔", "磨损"),
    ("价格", "性价比", "优惠"),
    ("售后", "客服", "维修", "退换", "质保"),
)


def _rank(item: AnalysisCorpusItem, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{item.review_id}".encode()).hexdigest()


def is_context_candidate(item: AnalysisCorpusItem) -> bool:
    text = item.normalized_text.strip()
    return (
        item.record_type == RecordType.REPLY
        and len(text) <= 24
        and any(marker in text for marker in CONTEXT_CANDIDATE_MARKERS)
    )


def _aspect_candidate_count(item: AnalysisCorpusItem) -> int:
    text = item.normalized_text
    return sum(any(marker in text for marker in markers) for markers in ASPECT_MARKER_GROUPS)


def sample_coverage(items: list[AnalysisCorpusItem]) -> dict[str, int]:
    return {
        "thread": sum(item.record_type == RecordType.THREAD for item in items),
        "reply": sum(item.record_type == RecordType.REPLY for item in items),
        "context_dependent_candidates": sum(is_context_candidate(item) for item in items),
        "short_text": sum(len(item.normalized_text) <= 12 for item in items),
        "medium_text": sum(13 <= len(item.normalized_text) <= 80 for item in items),
        "long_text": sum(len(item.normalized_text) >= 81 for item in items),
        "positive_candidates": sum(
            any(marker in item.normalized_text for marker in POSITIVE_MARKERS) for item in items
        ),
        "negative_candidates": sum(
            any(marker in item.normalized_text for marker in NEGATIVE_MARKERS) for item in items
        ),
        "single_aspect_candidates": sum(_aspect_candidate_count(item) == 1 for item in items),
        "multi_aspect_candidates": sum(_aspect_candidate_count(item) >= 2 for item in items),
    }


def select_corpus_items(
    queryset: QuerySet[AnalysisCorpusItem],
    *,
    limit: int | None,
    record_id: int | None = None,
    seed: int = DEFAULT_SAMPLE_SEED,
) -> list[AnalysisCorpusItem]:
    queryset = queryset.select_related("review", "quality", "product", "source")
    if record_id is not None:
        item = queryset.filter(review_id=record_id).first()
        return [item] if item is not None else []
    items = list(queryset)
    ranked = sorted(items, key=lambda item: _rank(item, seed))
    if limit is None or limit >= len(ranked):
        return ranked

    selected: list[AnalysisCorpusItem] = []
    selected_ids: set[int] = set()

    def pick(predicate: Callable[[AnalysisCorpusItem], bool]) -> None:
        candidate = next((item for item in ranked if item.review_id not in selected_ids and predicate(item)), None)
        if candidate is not None and len(selected) < limit:
            selected.append(candidate)
            selected_ids.add(candidate.review_id)

    def ensure(predicate: Callable[[AnalysisCorpusItem], bool]) -> None:
        if not any(predicate(item) for item in selected):
            pick(predicate)

    def ensure_count(predicate: Callable[[AnalysisCorpusItem], bool], count: int) -> None:
        while len(selected) < limit and sum(predicate(item) for item in selected) < count:
            before = len(selected)
            pick(predicate)
            if len(selected) == before:
                break

    ensure_count(is_context_candidate, 3)
    ensure(lambda item: len(item.normalized_text) <= 12)
    ensure(lambda item: 13 <= len(item.normalized_text) <= 80)
    ensure(lambda item: len(item.normalized_text) >= 81)
    ensure(lambda item: any(marker in item.normalized_text for marker in POSITIVE_MARKERS))
    ensure(lambda item: any(marker in item.normalized_text for marker in NEGATIVE_MARKERS))
    ensure(lambda item: _aspect_candidate_count(item) >= 2)
    ensure(lambda item: _aspect_candidate_count(item) == 1)
    ensure_count(lambda item: item.record_type == RecordType.THREAD, 5)
    ensure_count(lambda item: item.record_type == RecordType.REPLY, 10)

    for item in ranked:
        if len(selected) >= limit:
            break
        if item.review_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item.review_id)
    return selected
