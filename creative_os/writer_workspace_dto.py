"""Writer Workspace 面向 Web 的来源与版本 DTO。

本模块不读取文件、不修改领域状态，只定义稳定的跨层数据契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from creative_os.workspace_dto import Freshness


class WriterSourceRole(StrEnum):
    PUBLISHED = "published"
    CANONICAL = "canonical"
    APPROVED = "approved"
    WORKING_DRAFT = "working_draft"
    AGENT_PROPOSAL = "agent_proposal"


@dataclass(frozen=True, slots=True)
class WriterSourceDTO:
    role: WriterSourceRole
    label: str
    editable: bool
    source_key: str
    locator: str | None = None
    content_hash: str | None = None


@dataclass(frozen=True, slots=True)
class WriterVersionDTO:
    version: int
    content_hash: str
    created_at: str
    actor: str
    parent_version: int | None
    source_key: str


@dataclass(frozen=True, slots=True)
class WriterChapterDTO:
    project_id: str
    chapter_number: int
    title: str
    content: str
    source: WriterSourceDTO
    version: WriterVersionDTO | None
    freshness: Freshness
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WriterChapterEnvelope:
    chapter: WriterChapterDTO | None
    freshness: Freshness
    diagnostics: tuple[str, ...] = ()


def encode_writer_chapter(envelope: WriterChapterEnvelope) -> dict[str, Any]:
    """编码稳定 Web DTO；内部路径、哈希只作为来源详情字段返回。"""
    chapter = envelope.chapter
    if chapter is None:
        return {
            "chapter": None,
            "freshness": envelope.freshness.value,
            "diagnostics": list(envelope.diagnostics),
        }
    source = chapter.source
    version = chapter.version
    return {
        "chapter": {
            "project_id": chapter.project_id,
            "chapter_number": chapter.chapter_number,
            "title": chapter.title,
            "content": chapter.content,
            "source": {
                "role": source.role.value,
                "label": source.label,
                "editable": source.editable,
                "source_key": source.source_key,
                "locator": source.locator,
                "content_hash": source.content_hash,
            },
            "version": None if version is None else {
                "version": version.version,
                "created_at": version.created_at,
                "actor": version.actor,
                "parent_version": version.parent_version,
                "source_key": version.source_key,
                "content_hash": version.content_hash,
            },
            "freshness": chapter.freshness.value,
            "source_refs": list(chapter.source_refs),
        },
        "freshness": envelope.freshness.value,
        "diagnostics": list(envelope.diagnostics),
    }

