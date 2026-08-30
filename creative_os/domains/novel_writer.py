from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol

from creative_os.domains.narrative_decision import ChapterContract


class NovelWritingError(ValueError):
    """Writer 未能生成与准入绑定的正文。"""


@dataclass(frozen=True, slots=True)
class NovelWritingRequest:
    chapter_id: str
    chapter_contract: ChapterContract
    context_fingerprint: str
    instruction: str


@dataclass(frozen=True, slots=True)
class NovelDraft:
    content: str
    content_hash: str

    @classmethod
    def from_content(cls, content: str) -> "NovelDraft":
        if not content.strip():
            raise NovelWritingError("novel_draft_empty")
        return cls(content, hashlib.sha256(content.encode("utf-8")).hexdigest())


class NovelWriterPort(Protocol):
    def write(self, request: NovelWritingRequest, admission: object) -> NovelDraft: ...

