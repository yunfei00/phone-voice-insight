"""递归删除浏览器探测样本中的用户标识和秘密。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_NON_ALNUM = re.compile(r"[^a-z0-9]")
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_AUTH = re.compile(r"(?i)\b(?:Bearer|Basic)\s+[A-Za-z0-9+/_.=-]{8,}")
_URL = re.compile(r"(?i)https?://[^\s<>]+")

DENIED_KEYS = frozenset(
    {
        "nickname",
        "username",
        "userid",
        "uid",
        "guid",
        "pin",
        "userpin",
        "avatar",
        "userimage",
        "userimg",
        "imageurl",
        "imgurl",
        "userlevelid",
        "userlevelname",
        "userclient",
        "mobile",
        "phone",
        "email",
        "location",
        "address",
        "ip",
        "cookie",
        "authorization",
        "token",
        "accesstoken",
        "refreshtoken",
        "password",
        "passwd",
    }
)


def normalize_key(value: str) -> str:
    return _NON_ALNUM.sub("", value.casefold())


def is_denied_key(key: str) -> bool:
    normalized = normalize_key(key)
    return normalized in DENIED_KEYS or normalized.endswith("avatarurl") or normalized.endswith("profileurl")


def redact_sensitive_text(value: str) -> str:
    redacted = _EMAIL.sub("<redacted-email>", value)
    redacted = _PHONE.sub("<redacted-phone>", redacted)
    redacted = _JWT.sub("<redacted-token>", redacted)
    redacted = _AUTH.sub("<redacted-authorization>", redacted)
    return _URL.sub("<redacted-url>", redacted)


def sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): sanitize_value(item) for key, item in value.items() if not is_denied_key(str(key))}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_sensitive_text(str(value))


def find_denied_keys(value: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if is_denied_key(str(key)):
                findings.append(child_path)
            findings.extend(find_denied_keys(item, path=child_path))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            findings.extend(find_denied_keys(item, path=f"{path}[{index}]"))
    return findings
