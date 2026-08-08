"""Provider-neutral AI interface and response metadata."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ai.schemas.review_analysis import ReviewAnalysisInput


class AIProviderError(RuntimeError):
    def __init__(self, code: str, safe_message: str, *, retriable: bool = False) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.retriable = retriable


@dataclass(frozen=True)
class AIProviderResponse:
    provider: str
    model: str
    content: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    request_id: str = ""


class AIProvider(ABC):
    provider_name: str
    model: str

    @abstractmethod
    def analyze_review(
        self,
        request: ReviewAnalysisInput,
        *,
        prompt: str,
        validation_feedback: str = "",
    ) -> AIProviderResponse:
        """Return a raw structured response without persisting it."""
