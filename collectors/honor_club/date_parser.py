"""荣耀俱乐部帖子时间解析。"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HONOR_TIME_ZONE = ZoneInfo("Asia/Shanghai")

_FULL_PATTERN = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
)
_PARTIAL_PATTERN = re.compile(
    r"(?<!\d)(?P<month>\d{1,2})-(?P<day>\d{1,2})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
)


def _build_datetime(match: re.Match[str], year: int) -> datetime | None:
    try:
        return datetime(
            year=year,
            month=int(match.group("month")),
            day=int(match.group("day")),
            hour=int(match.group("hour")),
            minute=int(match.group("minute")),
            second=int(match.group("second") or 0),
            tzinfo=HONOR_TIME_ZONE,
        )
    except ValueError:
        return None


def parse_honor_datetime(value: str, *, reference: datetime | None = None) -> datetime | None:
    """解析完整或省略年份的时间；不可靠时返回 None。"""

    normalized = " ".join(value.split())
    full_match = _FULL_PATTERN.search(normalized)
    if full_match:
        return _build_datetime(full_match, int(full_match.group("year")))

    partial_match = _PARTIAL_PATTERN.search(normalized)
    if not partial_match or reference is None:
        return None

    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=HONOR_TIME_ZONE)
    else:
        reference = reference.astimezone(HONOR_TIME_ZONE)

    candidates = [
        candidate
        for year in (reference.year - 1, reference.year, reference.year + 1)
        if (candidate := _build_datetime(partial_match, year)) is not None
    ]
    if not candidates:
        return None

    # 回复通常不早于主题发布时间; 允许一天误差以兼容页面时间精度差异。
    plausible = [candidate for candidate in candidates if candidate >= reference - timedelta(days=1)]
    if plausible:
        return min(plausible, key=lambda candidate: abs(candidate - reference))
    return min(candidates, key=lambda candidate: abs(candidate - reference))
