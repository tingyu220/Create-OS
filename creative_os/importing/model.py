from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DocumentRole(StrEnum):
    CANON_CHAPTER = "canon_chapter"
    WORLD = "world"
    CHARACTER = "character"
    OUTLINE = "outline"
    HOOK = "hook"
    AUTHOR_CONTEXT = "author_context"
    ARCHIVE = "archive"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ImportDocument:
    relative_path: str
    extension: str
    size_bytes: int
    modified_at: float
    sha256: str


@dataclass(frozen=True, slots=True)
class ImportManifest:
    source_root: str
    documents: list[ImportDocument]
