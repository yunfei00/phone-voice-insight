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
_DAY_RELATIVE_PATTERN = re.compile(
    r"(?P<label>今天|昨天|前天)\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})(?::(?P<second>\d{2}))?"
)
_AGO_PATTERN = re.compile(r"(?P<amount>\d+)\s*(?P<unit>分钟|小时)前")


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
    """解析荣耀公开页时间；相对时间必须以页面抓取时间为基准。"""

    normalized = " ".join(value.split())
    full_match = _FULL_PATTERN.search(normalized)
    if full_match:
        return _build_datetime(full_match, int(full_match.group("year")))

    if reference is not None:
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=HONOR_TIME_ZONE)
        else:
            reference = reference.astimezone(HONOR_TIME_ZONE)

        if relative_match := _DAY_RELATIVE_PATTERN.search(normalized):
            days = {"今天": 0, "昨天": 1, "前天": 2}[relative_match.group("label")]
            target_day = (reference - timedelta(days=days)).date()
            try:
                return datetime(
                    target_day.year,
                    target_day.month,
                    target_day.day,
                    int(relative_match.group("hour")),
                    int(relative_match.group("minute")),
                    int(relative_match.group("second") or 0),
                    tzinfo=HONOR_TIME_ZONE,
                )
            except ValueError:
                return None

        if ago_match := _AGO_PATTERN.search(normalized):
            amount = int(ago_match.group("amount"))
            delta = timedelta(minutes=amount) if ago_match.group("unit") == "分钟" else timedelta(hours=amount)
            return reference - delta

    partial_match = _PARTIAL_PATTERN.search(normalized)
    if not partial_match or reference is None:
        return None

    candidates = [
        candidate
        for year in (reference.year - 1, reference.year, reference.year + 1)
        if (candidate := _build_datetime(partial_match, year)) is not None
    ]
    if not candidates:
        return None

    # 详情页省略年份时, 以抓取时间选择最近且不过分位于未来的年份。
    plausible = [candidate for candidate in candidates if candidate <= reference + timedelta(days=1)]
    if plausible:
        return min(plausible, key=lambda candidate: abs(candidate - reference))
    return min(candidates, key=lambda candidate: abs(candidate - reference))


def honor_datetime_failure_reason(value: str, *, reference: datetime | None = None) -> str:
    """Return a stable reason code when a public timestamp cannot be normalized."""

    normalized = " ".join(value.split())
    if not normalized:
        return "source_time_missing"
    if re.search(r"\d+\s*天前", normalized):
        return "relative_day_without_time_precision"
    if reference is None and (_PARTIAL_PATTERN.search(normalized) or _DAY_RELATIVE_PATTERN.search(normalized)):
        return "reference_time_required"
    if (
        _FULL_PATTERN.search(normalized)
        or _PARTIAL_PATTERN.search(normalized)
        or _DAY_RELATIVE_PATTERN.search(normalized)
    ):
        return "invalid_time_value"
    return "unsupported_time_format"
