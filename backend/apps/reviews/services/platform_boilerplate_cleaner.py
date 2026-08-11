"""Remove only confirmed, fixed platform-injected declaration lines."""

# ruff: noqa: RUF001

from __future__ import annotations

from dataclasses import dataclass

from apps.reviews.services.text_normalizer import normalize_text

PLATFORM_BOILERPLATE_LINES = frozenset({"作者声明：作品含AI生成内容"})


@dataclass(frozen=True)
class BoilerplateCleaningResult:
    text: str
    removed_lines: tuple[str, ...]


def clean_platform_boilerplate(value: str | None) -> BoilerplateCleaningResult:
    """Return normalized text without exact, high-confidence injected lines."""

    normalized = normalize_text(value)
    kept: list[str] = []
    removed: list[str] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped in PLATFORM_BOILERPLATE_LINES:
            removed.append(stripped)
        else:
            kept.append(line)
    return BoilerplateCleaningResult(normalize_text("\n".join(kept)), tuple(removed))
