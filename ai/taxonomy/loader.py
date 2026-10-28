"""Versioned, strictly validated business taxonomy loader."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

TAXONOMY_VERSION = "1.0.0"
_TAXONOMY_PATH = Path(__file__).with_name("structured_analysis_v1.json")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TaxonomyTag(StrictModel):
    tag_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]*(\.[A-Z][A-Z0-9_]*)?$")
    parent_id: str | None
    name: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=500)
    positive_examples: list[str] = Field(min_length=1)
    negative_examples: list[str] = Field(min_length=1)
    confused_with: list[str]
    enabled: bool
    taxonomy_version: str
    children: list[TaxonomyTag] = Field(default_factory=list)


class TaxonomyDefinition(StrictModel):
    taxonomy_version: str
    name: str
    domains: list[TaxonomyTag] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_tree(self) -> TaxonomyDefinition:
        if self.taxonomy_version != TAXONOMY_VERSION:
            raise ValueError("unsupported taxonomy_version")
        seen: set[str] = set()
        domain_ids = {domain.tag_id for domain in self.domains}
        for domain in self.domains:
            if domain.parent_id is not None or "." in domain.tag_id:
                raise ValueError(f"invalid top-level domain: {domain.tag_id}")
            if domain.taxonomy_version != self.taxonomy_version:
                raise ValueError(f"taxonomy version mismatch: {domain.tag_id}")
            if domain.tag_id in seen:
                raise ValueError(f"duplicate tag: {domain.tag_id}")
            seen.add(domain.tag_id)
            for child in domain.children:
                if child.children:
                    raise ValueError(f"only two taxonomy levels are supported: {child.tag_id}")
                if child.parent_id != domain.tag_id or not child.tag_id.startswith(f"{domain.tag_id}."):
                    raise ValueError(f"invalid parent relation: {child.tag_id}")
                if child.taxonomy_version != self.taxonomy_version:
                    raise ValueError(f"taxonomy version mismatch: {child.tag_id}")
                if child.tag_id in seen:
                    raise ValueError(f"duplicate tag: {child.tag_id}")
                seen.add(child.tag_id)
                invalid_confusions = set(child.confused_with) - (seen | domain_ids | _all_declared_ids(self.domains))
                if invalid_confusions:
                    raise ValueError(f"unknown confused_with tag: {sorted(invalid_confusions)[0]}")
        return self

    @property
    def domain_ids(self) -> frozenset[str]:
        return frozenset(domain.tag_id for domain in self.domains if domain.enabled)

    @property
    def topic_parent_map(self) -> dict[str, str]:
        return {
            child.tag_id: domain.tag_id
            for domain in self.domains
            if domain.enabled
            for child in domain.children
            if child.enabled
        }


def _all_declared_ids(domains: list[TaxonomyTag]) -> set[str]:
    return {tag.tag_id for domain in domains for tag in (domain, *domain.children)}


@lru_cache(maxsize=4)
def load_taxonomy(version: str = TAXONOMY_VERSION) -> TaxonomyDefinition:
    if version != TAXONOMY_VERSION:
        raise ValueError(f"TAXONOMY_VERSION_NOT_FOUND:{version}")
    payload = json.loads(_TAXONOMY_PATH.read_text(encoding="utf-8"))
    return TaxonomyDefinition.model_validate(payload)


def validate_tag_relation(aspect_code: str, topic_code: str, *, version: str = TAXONOMY_VERSION) -> bool:
    taxonomy = load_taxonomy(version)
    return aspect_code in taxonomy.domain_ids and taxonomy.topic_parent_map.get(topic_code) == aspect_code
