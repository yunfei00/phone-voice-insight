"""Review data-governance services."""

from apps.reviews.services.constants import CORPUS_VERSION, GOVERNANCE_PROCESSOR_VERSION
from apps.reviews.services.governance_pipeline import GovernanceProcessor, process_reviews

__all__ = (
    "CORPUS_VERSION",
    "GOVERNANCE_PROCESSOR_VERSION",
    "GovernanceProcessor",
    "process_reviews",
)
