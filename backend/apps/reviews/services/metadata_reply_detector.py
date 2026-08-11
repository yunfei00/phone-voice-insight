"""Detect replies that contain only version, model, or parameter metadata."""

# ruff: noqa: RUF001

from __future__ import annotations

import re
from dataclasses import dataclass

from apps.reviews.services.text_normalizer import normalize_text

_VERSION_TOKEN = r"(?:最新版|[A-Za-z]*\d+(?:\.\d+){0,3}(?:[A-Za-z0-9_-]+)?)"
_VERSION_ONLY = re.compile(
    rf"^(?:(?:系统|软件)?版本(?:是|为)?|刚升级(?:到)?|升级到)?\s*({_VERSION_TOKEN})\s*(?:版本)?(?:的)?[。.!！]?$",
    re.IGNORECASE,
)
_NAMED_VERSION_ONLY = re.compile(
    r"^(?:(?:系统|软件)?版本(?:是|为)?|刚升级(?:到)?|升级到)\s*"
    r"([A-Za-z][A-Za-z0-9_.-]*(?:\s+\d+(?:\.\d+){0,3})?)\s*(?:版本)?(?:的)?[。.!！]?$",
    re.IGNORECASE,
)
_MODEL_ONLY = re.compile(
    r"^(?:设备|手机)?型号(?:是|为)?\s*([A-Za-z0-9][A-Za-z0-9+_. -]{0,40})[。.!！]?$",
    re.IGNORECASE,
)
_PARAMETER_ONLY = re.compile(r"^(\d{1,3}\s*[+＋]\s*\d{2,4}(?:gb)?)\s*(?:版本)?[。.!！]?$", re.IGNORECASE)


@dataclass(frozen=True)
class MetadataReply:
    is_metadata_only: bool
    candidate_metadata: dict[str, str]


def detect_metadata_reply(value: str | None) -> MetadataReply:
    """Classify only whole-text metadata answers; experience statements never match."""

    text = normalize_text(value)
    version_match = _VERSION_ONLY.fullmatch(text)
    if version_match:
        return MetadataReply(True, {"software_version": version_match.group(1)})
    named_version_match = _NAMED_VERSION_ONLY.fullmatch(text)
    if named_version_match:
        return MetadataReply(True, {"software_version": named_version_match.group(1)})
    model_match = _MODEL_ONLY.fullmatch(text)
    if model_match:
        return MetadataReply(True, {"device_model": model_match.group(1).strip()})
    parameter_match = _PARAMETER_ONLY.fullmatch(text)
    if parameter_match:
        return MetadataReply(True, {"device_parameter": re.sub(r"\s+", "", parameter_match.group(1))})
    return MetadataReply(False, {})
