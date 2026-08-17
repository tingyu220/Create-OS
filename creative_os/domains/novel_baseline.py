from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from creative_os.domains.novel_importer import ClassifiedNovelImport
from creative_os.importing.model import DocumentRole


CHAPTER_PATTERN = re.compile(r"第\s*(\d+)\s*章(?:\s*[:：]\s*(.+))?")


@dataclass(frozen=True, slots=True)
class BaselineArtifact:
    title: str
    content: str
    source_path: str
    source_hash: str
    heading: str
    status: str = "candidate"


@dataclass(frozen=True, slots=True)
class CanonChapter:
    number: int
    title: str
    text: str
    source_path: str
    source_hash: str


@dataclass(frozen=True, slots=True)
class NovelBaselineDraft:
    canon_chapters: list[CanonChapter]
    world_rules: list[BaselineArtifact]
    characters: list[BaselineArtifact]
    plot_milestones: list[BaselineArtifact]
    hooks: list[BaselineArtifact]
    style_constraints: list[BaselineArtifact]
    knowledge_candidates: list[BaselineArtifact]


def build_novel_baseline(imported: ClassifiedNovelImport) -> NovelBaselineDraft:
    source_root = Path(imported.manifest.source_root)
    buckets: dict[DocumentRole, list[BaselineArtifact]] = {role: [] for role in DocumentRole}
    chapters: list[CanonChapter] = []
    for classified in imported.documents:
        if classified.role in {DocumentRole.ARCHIVE, DocumentRole.UNKNOWN}:
            continue
        document = classified.document
        content = (source_root / document.relative_path).read_text(encoding="utf-8")
        if classified.role == DocumentRole.CANON_CHAPTER:
            chapter = _chapter(document.relative_path, document.sha256, content)
            if chapter is not None:
                chapters.append(chapter)
            continue
        buckets[classified.role].append(
            BaselineArtifact(
                title=Path(document.relative_path).stem,
                content=content,
                source_path=document.relative_path,
                source_hash=document.sha256,
                heading=_first_heading(content),
            )
        )

    selected = [
        *buckets[DocumentRole.WORLD],
        *buckets[DocumentRole.CHARACTER],
        *buckets[DocumentRole.OUTLINE],
        *buckets[DocumentRole.HOOK],
        *buckets[DocumentRole.AUTHOR_CONTEXT],
    ]
    return NovelBaselineDraft(
        canon_chapters=sorted(chapters, key=lambda item: item.number),
        world_rules=buckets[DocumentRole.WORLD],
        characters=buckets[DocumentRole.CHARACTER],
        plot_milestones=buckets[DocumentRole.OUTLINE],
        hooks=buckets[DocumentRole.HOOK],
        style_constraints=buckets[DocumentRole.AUTHOR_CONTEXT],
        knowledge_candidates=selected,
    )


def _chapter(source_path: str, source_hash: str, text: str) -> CanonChapter | None:
    match = CHAPTER_PATTERN.search(Path(source_path).stem) or CHAPTER_PATTERN.search(text)
    if match is None:
        return None
    return CanonChapter(
        number=int(match.group(1)),
        title=(match.group(2) or Path(source_path).stem).strip(),
        text=text,
        source_path=source_path,
        source_hash=source_hash,
    )


def _first_heading(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""
