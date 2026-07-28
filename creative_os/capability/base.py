from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from creative_os.engine.context import Context
from creative_os.foundation.task import Task


class ResultKind(StrEnum):
    WRITING = "writing"
    REVIEW = "review"
    RESEARCH = "research"


@dataclass(slots=True)
class Issue:
    code: str
    message: str
    severity: str = "medium"


@dataclass(slots=True)
class KnowledgeDraft:
    title: str
    body: str
    tags: set[str] = field(default_factory=set)
    source: str | None = None


@dataclass(slots=True)
class Result:
    content: str
    kind: ResultKind = ResultKind.WRITING
    issues: list[Issue] = field(default_factory=list)
    follow_up_tasks: list[Task] = field(default_factory=list)
    knowledge_drafts: list[KnowledgeDraft] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


class Capability(Protocol):
    def run(self, context: Context) -> Result:
        raise NotImplementedError
