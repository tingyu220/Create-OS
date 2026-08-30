from __future__ import annotations

import hashlib
from pathlib import Path

from creative_os.importing.model import ImportDocument, ImportManifest


SUPPORTED_EXTENSIONS = {".md", ".json"}


def scan_source(source_root: str | Path) -> ImportManifest:
    root = Path(source_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    documents: list[ImportDocument] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if not path.is_file() or path.suffix.casefold() not in SUPPORTED_EXTENSIONS:
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        stat = path.stat()
        documents.append(
            ImportDocument(
                relative_path=relative.as_posix(),
                extension=path.suffix.casefold(),
                size_bytes=stat.st_size,
                modified_at=stat.st_mtime,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            )
        )
    return ImportManifest(source_root=str(root), documents=documents)
