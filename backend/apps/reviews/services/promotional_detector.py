"""High-confidence promotional and campaign content detection."""

from __future__ import annotations

from apps.reviews.services.text_normalizer import normalize_text

_TITLE_MARKERS = ("活动", "抽奖", "有奖", "招募", "赢好礼", "报名", "福利")
_ACTION_MARKERS = ("参与活动", "点击报名", "立即报名", "赢取", "奖品", "活动时间", "报名时间")
_COMMERCE_MARKERS = ("购机", "荣耀商城", "赠价值", "返现", "免息", "立即购买", "优惠", "http")
_LAUNCH_MARKERS = ("全面曝光", "正式发布", "首发", "开售", "新品发布")


def is_promotional_content(*, title: str | None, content: str | None, is_official: bool) -> bool:
    normalized_title = normalize_text(title)
    normalized_content = normalize_text(content)
    combined = f"{normalized_title}\n{normalized_content}"
    if sum(marker in combined for marker in _COMMERCE_MARKERS) >= 2:
        return True
    if sum(marker in combined for marker in _LAUNCH_MARKERS) >= 3:
        return True
    title_hits = sum(marker in normalized_title for marker in _TITLE_MARKERS)
    action_hits = sum(marker in normalized_content for marker in _ACTION_MARKERS)
    if not title_hits:
        return False
    return is_official or title_hits + action_hits >= 2
