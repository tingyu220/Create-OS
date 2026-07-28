from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class DomainPackage:
    name: str
    schema: list[str]
    rules: list[str]
    workflow: list[str]
    templates: dict[str, str] = field(default_factory=dict)
    default_retrieval_tags: set[str] = field(default_factory=set)

