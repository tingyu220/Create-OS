from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from creative_os.importing.model import DocumentRole, ImportDocument, ImportManifest


ARCHIVE_MARKERS = {"fix", "_archive", "archive", "backup", "backups", "备份", "废稿"}


@dataclass(frozen=True, slots=True)
class ClassifiedDocument:
    document: ImportDocument
    role: DocumentRole


@dataclass(frozen=True, slots=True)
class ClassifiedNovelImport:
    manifest: ImportManifest
    documents: list[ClassifiedDocument]


def default_novel_mapping() -> dict[str, str]:
    return {
        "04_Chapters": DocumentRole.CANON_CHAPTER.value,
        "00_Worldview": DocumentRole.WORLD.value,
        "01_Characters": DocumentRole.CHARACTER.value,
        "02_Plot": DocumentRole.OUTLINE.value,
        "03_Hooks": DocumentRole.HOOK.value,
        "05_Context": DocumentRole.AUTHOR_CONTEXT.value,
        "06_重构方案.md": DocumentRole.OUTLINE.value,
        "核心框架.md": DocumentRole.WORLD.value,
        "Novel_README.md": DocumentRole.AUTHOR_CONTEXT.value,
    }


def classify_novel_documents(manifest: ImportManifest, mapping: dict[str, str] | None = None) -> ClassifiedNovelImport:
    normalized_mapping = {
        _normalize_path(prefix): DocumentRole(role)
        for prefix, role in (mapping or default_novel_mapping()).items()
    }
    documents = [
        ClassifiedDocument(document=document, role=_classify(document.relative_path, normalized_mapping))
        for document in manifest.documents
    ]
    return ClassifiedNovelImport(manifest=manifest, documents=documents)


def role_of(imported: ClassifiedNovelImport, relative_path: str) -> str:
    normalized = _normalize_path(relative_path)
    for document in imported.documents:
        if document.document.relative_path == normalized:
            return document.role.value
    raise KeyError(relative_path)


def _classify(relative_path: str, mapping: dict[str, DocumentRole]) -> DocumentRole:
    parts = PurePosixPath(relative_path).parts
    if any(part.casefold() in ARCHIVE_MARKERS for part in parts):
        return DocumentRole.ARCHIVE
    normalized = _normalize_path(relative_path)
    matching_prefixes = [prefix for prefix in mapping if normalized == prefix or normalized.startswith(f"{prefix}/")]
    if not matching_prefixes:
        return DocumentRole.UNKNOWN
    return mapping[max(matching_prefixes, key=len)]


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")
