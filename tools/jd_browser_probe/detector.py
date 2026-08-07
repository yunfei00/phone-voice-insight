"""根据 URL 和响应结构识别可能的京东评价请求。"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from collectors.base import CollectorError
from collectors.jd.jsonp import parse_json_or_jsonp

from tools.jd_browser_probe.sanitizer import normalize_key

URL_KEYWORDS = (
    "comment",
    "comments",
    "review",
    "reviews",
    "evaluate",
    "evaluation",
    "productpagecomments",
)
JSON_CONTENT_TYPES = frozenset(
    {
        "application/json",
        "application/javascript",
        "text/javascript",
        # Some JD XHRs label JSON as text/json or text/plain. The strict
        # JSON/JSONP parser handles bodies in memory and discards failures.
        "text/json",
        "text/plain",
    }
)
SAFE_QUERY_NAMES = frozenset(
    {
        "productid",
        "referenceid",
        "skuid",
        "page",
        "pagenum",
        "pagesize",
        "sorttype",
        "score",
        "callback",
    }
)
SENSITIVE_QUERY_NAMES = frozenset(
    {
        "token",
        "accesstoken",
        "auth",
        "authorization",
        "sign",
        "signature",
        "h5st",
        "fingerprint",
        "eid",
        "uuid",
        "pin",
    }
)
_DIGITS = re.compile(r"\d{1,24}")
_SHORT_VALUE = re.compile(r"[A-Za-z0-9_.-]{1,32}")
_CALLBACK = re.compile(r"[A-Za-z_$][A-Za-z0-9_$.]{0,79}")
SEMANTIC_KEYS: dict[str, frozenset[str]] = {
    "comment_id": frozenset({"commentid", "commentidstr", "evaluationid", "reviewid"}),
    "content": frozenset({"content", "commentcontent", "reviewcontent", "text"}),
    "rating": frozenset({"score", "rating", "star", "stars"}),
    "time": frozenset({"creationtime", "createdat", "createdtime", "commenttime", "referencetime"}),
    "sku": frozenset({"referenceid", "skuid", "productid", "wareid"}),
    "color": frozenset({"productcolor", "color"}),
    "size": frozenset({"productsize", "size", "specification"}),
    "append": frozenset({"appendcomment", "aftercomment", "afterusercomment", "additionalcomment"}),
}


@dataclass(frozen=True)
class ArrayObservation:
    path: str
    length: int
    item_keys: tuple[str, ...]
    semantic_hints: tuple[str, ...]


@dataclass(frozen=True)
class DetectionResult:
    top_level_keys: tuple[str, ...]
    arrays: tuple[ArrayObservation, ...]
    url_keyword_hits: tuple[str, ...]
    score: int
    reasons: tuple[str, ...]
    candidate: bool
    sample_items: tuple[dict[str, Any], ...]

    def stage_a_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result.pop("sample_items", None)
        return result


def normalized_content_type(value: str) -> str:
    return value.partition(";")[0].strip().casefold()


def is_json_like_content_type(value: str) -> bool:
    return normalized_content_type(value) in JSON_CONTENT_TYPES


def is_jd_host(host: str) -> bool:
    normalized = host.casefold().rstrip(".")
    return normalized in {"jd.com", "jd.cn"} or normalized.endswith((".jd.com", ".jd.cn"))


def sensitive_query_names(url: str) -> tuple[str, ...]:
    names = {
        name
        for key, _value in parse_qsl(urlparse(url).query, keep_blank_values=True)
        if (name := normalize_key(key)) in SENSITIVE_QUERY_NAMES
    }
    return tuple(sorted(names))


def _safe_query_value(name: str, value: str) -> str:
    normalized = normalize_key(name)
    if normalized not in SAFE_QUERY_NAMES or normalized in SENSITIVE_QUERY_NAMES:
        return "<redacted>"
    if normalized in {"productid", "referenceid", "skuid", "page", "pagenum", "pagesize", "score"}:
        return value if _DIGITS.fullmatch(value) else "<redacted>"
    if normalized == "sorttype":
        return value if _SHORT_VALUE.fullmatch(value) else "<redacted>"
    if normalized == "callback":
        return value if _CALLBACK.fullmatch(value) else "<redacted>"
    return "<redacted>"


def redact_url(url: str) -> str:
    parsed = urlparse(url)
    redacted_query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        redacted_query.append((key, _safe_query_value(key, value)))
    query = urlencode(redacted_query, doseq=True, quote_via=quote, safe="<>")
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))


def query_parameter_schema(url: str) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for key, value in parse_qsl(urlparse(url).query, keep_blank_values=True):
        if key in seen:
            continue
        seen.add(key)
        example = _safe_query_value(key, value)
        result.append({"name": key, "example": example, "meaning": "未确认"})
    return result


def build_network_entry(
    *,
    method: str,
    url: str,
    status: int,
    content_type: str,
    resource_type: str,
    timestamp: str | None = None,
) -> dict[str, Any] | None:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if resource_type not in {"xhr", "fetch"} or not is_jd_host(host):
        return None
    return {
        "timestamp": timestamp or datetime.now(UTC).isoformat(),
        "method": method.upper(),
        "url": redact_url(url),
        "host": host.casefold(),
        "path": parsed.path,
        "status": status,
        "content_type": normalized_content_type(content_type),
        "resource_type": resource_type,
    }


def parse_json_body(body: str | bytes) -> Any | None:
    try:
        return parse_json_or_jsonp(body)
    except (CollectorError, UnicodeDecodeError):
        return None


def _semantic_hints(keys: set[str]) -> tuple[str, ...]:
    normalized = {normalize_key(key) for key in keys}
    return tuple(sorted(name for name, candidates in SEMANTIC_KEYS.items() if normalized.intersection(candidates)))


def _walk_arrays(value: Any, *, path: str = "$", depth: int = 0) -> list[tuple[ArrayObservation, list[Any]]]:
    if depth > 6:
        return []
    found: list[tuple[ArrayObservation, list[Any]]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(_walk_arrays(item, path=f"{path}.{key}", depth=depth + 1))
    elif isinstance(value, list):
        item_keys: set[str] = set()
        for item in value[:3]:
            if isinstance(item, dict):
                item_keys.update(str(key) for key in item)
        observation = ArrayObservation(
            path=path,
            length=len(value),
            item_keys=tuple(sorted(item_keys)),
            semantic_hints=_semantic_hints(item_keys),
        )
        found.append((observation, value))
        for index, item in enumerate(value[:3]):
            found.extend(_walk_arrays(item, path=f"{path}[{index}]", depth=depth + 1))
    return found


def inspect_payload(payload: Any, *, url: str) -> DetectionResult:
    top_level_keys = tuple(sorted(str(key) for key in payload)) if isinstance(payload, dict) else ()
    observed_arrays = _walk_arrays(payload)
    url_lower = url.casefold()
    keyword_hits = tuple(keyword for keyword in URL_KEYWORDS if keyword in url_lower)
    best_observation: ArrayObservation | None = None
    best_items: list[Any] = []
    for observation, items in observed_arrays:
        if best_observation is None or (len(observation.semantic_hints), observation.length) > (
            len(best_observation.semantic_hints),
            best_observation.length,
        ):
            best_observation = observation
            best_items = items

    reasons: list[str] = []
    score = 0
    if keyword_hits:
        score += 3
        reasons.append("URL contains review-related keyword")
    if best_observation and best_observation.length:
        score += 1
        reasons.append("response contains non-empty array")
        score += len(best_observation.semantic_hints)
        if best_observation.semantic_hints:
            reasons.append("array item keys contain review-like concepts")
    candidate = bool(keyword_hits) or bool(
        best_observation and best_observation.length and len(best_observation.semantic_hints) >= 3
    )
    samples = tuple(item for item in best_items[:3] if isinstance(item, dict))
    return DetectionResult(
        top_level_keys=top_level_keys,
        arrays=tuple(observation for observation, _items in observed_arrays),
        url_keyword_hits=keyword_hits,
        score=score,
        reasons=tuple(reasons),
        candidate=candidate,
        sample_items=samples,
    )
