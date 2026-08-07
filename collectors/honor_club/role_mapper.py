"""荣耀俱乐部公开作者身份到统一角色的映射。"""

import re

AUTHOR_ROLE_USER = "USER"
AUTHOR_ROLE_OFFICIAL = "OFFICIAL"
AUTHOR_ROLE_MODERATOR = "MODERATOR"
AUTHOR_ROLE_EXPERT = "EXPERT"
AUTHOR_ROLE_UNKNOWN = "UNKNOWN"

_OFFICIAL_MARKERS = ("荣耀俱乐部团队", "荣耀答答团")
_MODERATOR_MARKERS = ("实习版主", "分区版主", "版主")
_EXPERT_MARKERS = ("玩机达人", "摄影达人", "达人")
_USER_LEVEL_PATTERN = re.compile(r"\bLV(?:10|[1-9])\b", re.IGNORECASE)


def normalize_role_text(value: str) -> str:
    return " ".join(value.split()).strip()


def map_author_role(author_role_text: str) -> str:
    """按保守规则映射角色；无法明确识别时返回 UNKNOWN。"""

    normalized = normalize_role_text(author_role_text)
    if any(marker in normalized for marker in _OFFICIAL_MARKERS):
        return AUTHOR_ROLE_OFFICIAL
    if any(marker in normalized for marker in _MODERATOR_MARKERS):
        return AUTHOR_ROLE_MODERATOR
    if any(marker in normalized for marker in _EXPERT_MARKERS):
        return AUTHOR_ROLE_EXPERT
    if _USER_LEVEL_PATTERN.search(normalized):
        return AUTHOR_ROLE_USER
    return AUTHOR_ROLE_UNKNOWN


def is_official_role(author_role: str) -> bool:
    return author_role == AUTHOR_ROLE_OFFICIAL
