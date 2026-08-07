"""严格解析 JSON 或 JSONP，不执行响应中的代码。"""

from __future__ import annotations

import json
import re
from typing import Any

from collectors.base import CollectorError

_CALLBACK_PATTERN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$.]*")
_JSONP_PATTERN = re.compile(r"^\s*(?P<callback>[A-Za-z_$][A-Za-z0-9_$.]*)\s*\(\s*(?P<payload>[\s\S]*)\s*\)\s*;?\s*$")


def parse_json_or_jsonp(content: str | bytes, *, expected_callback: str | None = None) -> Any:
    text = content.decode("utf-8", errors="strict") if isinstance(content, bytes) else content
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    match = _JSONP_PATTERN.fullmatch(stripped)
    if match is None:
        raise CollectorError("响应既不是合法 JSON, 也不是合法 JSONP", code="RESPONSE_FORMAT_CHANGED")
    callback = match.group("callback")
    if _CALLBACK_PATTERN.fullmatch(callback) is None or (expected_callback and callback != expected_callback):
        raise CollectorError("JSONP callback 与请求不一致", code="RESPONSE_FORMAT_CHANGED")
    try:
        return json.loads(match.group("payload"))
    except json.JSONDecodeError as exc:
        raise CollectorError("JSONP 包装内不是合法 JSON", code="RESPONSE_FORMAT_CHANGED") from exc
