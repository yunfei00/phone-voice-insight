"""Validate that every evidence span is verbatim and traceable."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

from ai.schemas.review_analysis import ReviewAnalysisInput, ReviewAnalysisOutput

_HTML_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]+);")
_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\u2060\ufeff")


@dataclass(frozen=True)
class EvidenceValidationError:
    aspect: str
    field: str
    message: str


@dataclass(frozen=True)
class _MappedText:
    text: str
    raw_ranges: tuple[tuple[int, int], ...]


def _decoded_chars(raw_text: str) -> list[tuple[str, int, int]]:
    chars: list[tuple[str, int, int]] = []
    cursor = 0
    for match in _HTML_ENTITY.finditer(raw_text):
        chars.extend((char, index, index + 1) for index, char in enumerate(raw_text[cursor : match.start()], cursor))
        decoded = html.unescape(match.group())
        chars.extend((char, match.start(), match.end()) for char in decoded)
        cursor = match.end()
    chars.extend((char, index, index + 1) for index, char in enumerate(raw_text[cursor:], cursor))
    return chars


def _nfc_chars(chars: list[tuple[str, int, int]]) -> list[tuple[str, int, int]]:
    result: list[tuple[str, int, int]] = []
    index = 0
    while index < len(chars):
        group = [chars[index]]
        index += 1
        while index < len(chars) and unicodedata.combining(chars[index][0]):
            group.append(chars[index])
            index += 1
        normalized = unicodedata.normalize("NFC", "".join(char for char, _start, _end in group))
        start = group[0][1]
        end = group[-1][2]
        result.extend((char, start, end) for char in normalized)
    return result


def _normalize_with_mapping(raw_text: str) -> _MappedText:
    chars = [item for item in _nfc_chars(_decoded_chars(raw_text)) if item[0] not in _ZERO_WIDTH]
    newline_normalized: list[tuple[str, int, int]] = []
    index = 0
    while index < len(chars):
        char, start, end = chars[index]
        if char == "\r":
            if index + 1 < len(chars) and chars[index + 1][0] == "\n":
                end = chars[index + 1][2]
                index += 1
            newline_normalized.append(("\n", start, end))
        else:
            newline_normalized.append((char, start, end))
        index += 1

    collapsed: list[tuple[str, int, int]] = []
    line: list[tuple[str, int, int]] = []

    def flush_line() -> None:
        compacted: list[tuple[str, int, int]] = []
        cursor = 0
        while cursor < len(line):
            char, start, end = line[cursor]
            if char.isspace():
                while cursor + 1 < len(line) and line[cursor + 1][0].isspace():
                    cursor += 1
                    end = line[cursor][2]
                compacted.append((" ", start, end))
            else:
                compacted.append((char, start, end))
            cursor += 1
        while compacted and compacted[0][0] == " ":
            compacted.pop(0)
        while compacted and compacted[-1][0] == " ":
            compacted.pop()
        collapsed.extend(compacted)

    for item in newline_normalized:
        if item[0] == "\n":
            flush_line()
            line.clear()
            collapsed.append(item)
        else:
            line.append(item)
    flush_line()
    while collapsed and collapsed[0][0].isspace():
        collapsed.pop(0)
    while collapsed and collapsed[-1][0].isspace():
        collapsed.pop()

    limited: list[tuple[str, int, int]] = []
    consecutive_newlines = 0
    for item in collapsed:
        if item[0] == "\n":
            consecutive_newlines += 1
            if consecutive_newlines > 2:
                continue
        else:
            consecutive_newlines = 0
        limited.append(item)
    return _MappedText(
        "".join(char for char, _start, _end in limited),
        tuple((start, end) for _char, start, end in limited),
    )


def map_normalized_evidence_to_raw(raw_text: str, evidence_text: str) -> str | None:
    """Return one raw contiguous span only when deterministic normalization proves equivalence."""

    if evidence_text in raw_text:
        return evidence_text
    mapped = _normalize_with_mapping(raw_text)
    offset = mapped.text.find(evidence_text)
    if offset < 0 or not evidence_text:
        return None
    start = mapped.raw_ranges[offset][0]
    end = mapped.raw_ranges[offset + len(evidence_text) - 1][1]
    raw_span = raw_text[start:end]
    return raw_span if _normalize_with_mapping(raw_span).text == evidence_text else None


def reconcile_evidence_spans(
    request: ReviewAnalysisInput,
    output: ReviewAnalysisOutput,
    *,
    raw_content: str | None = None,
    raw_context_sources: dict[str, str] | None = None,
) -> ReviewAnalysisOutput:
    current_raw = request.content if raw_content is None else raw_content
    contexts = {
        request.thread_review_id: request.thread_content,
        request.parent_review_id: request.parent_content,
    }
    contexts.update(raw_context_sources or {})
    aspects = []
    for item in output.aspects:
        evidence = map_normalized_evidence_to_raw(current_raw, item.evidence_text) or item.evidence_text
        context_evidence = item.context_evidence_text
        if item.context_evidence_review_id and context_evidence:
            referenced = contexts.get(item.context_evidence_review_id, "")
            context_evidence = map_normalized_evidence_to_raw(referenced, context_evidence) or context_evidence
        aspects.append(item.model_copy(update={"evidence_text": evidence, "context_evidence_text": context_evidence}))
    return output.model_copy(update={"aspects": aspects})


def validate_evidence(
    request: ReviewAnalysisInput,
    output: ReviewAnalysisOutput,
    *,
    raw_content: str | None = None,
    raw_context_sources: dict[str, str] | None = None,
) -> tuple[EvidenceValidationError, ...]:
    current_content = request.content if raw_content is None else raw_content
    context_sources = {
        request.thread_review_id: request.thread_content,
        request.parent_review_id: request.parent_content,
    }
    context_sources.update(raw_context_sources or {})
    errors: list[EvidenceValidationError] = []
    for item in output.aspects:
        aspect = item.aspect.value
        if item.evidence_text not in current_content:
            errors.append(EvidenceValidationError(aspect, "evidence_text", "evidence is not verbatim current content"))
        if item.context_dependent:
            if not item.context_evidence_review_id or not item.context_evidence_text:
                errors.append(EvidenceValidationError(aspect, "context_evidence", "context evidence is required"))
                continue
            referenced = context_sources.get(item.context_evidence_review_id, "")
            if not referenced or item.context_evidence_text not in referenced:
                errors.append(
                    EvidenceValidationError(
                        aspect, "context_evidence_text", "context evidence is not verbatim referenced content"
                    )
                )
        elif item.context_evidence_review_id or item.context_evidence_text:
            errors.append(
                EvidenceValidationError(aspect, "context_dependent", "context evidence requires context_dependent")
            )
    return tuple(errors)
