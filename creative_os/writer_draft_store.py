"""Working Draft 版本存储；正式章节文件永远只读。"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from creative_os.domains.project_authority import project_authority_lock
from creative_os.writer_workspace_dto import WriterVersionDTO


class DraftConflictError(ValueError):
    pass


class DraftNotFoundError(KeyError):
    pass


class WriterDraftStore:
    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root)
        self.root = self.project_root / ".creative_os" / "writer" / "drafts"

    def versions(self, chapter_number: int) -> tuple[WriterVersionDTO, ...]:
        path = self._path(chapter_number)
        if not path.exists():
            return ()
        return tuple(self._decode(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())

    def current(self, chapter_number: int) -> tuple[WriterVersionDTO, str] | None:
        versions = self.versions(chapter_number)
        if not versions:
            return None
        record = json.loads(self._path(chapter_number).read_text(encoding="utf-8").splitlines()[-1])
        return versions[-1], record["content"]

    def save(self, chapter_number: int, content: str, *, actor: str, expected_version: int | None = None) -> WriterVersionDTO:
        if chapter_number <= 0:
            raise ValueError("chapter_number_invalid")
        if not actor.strip():
            raise ValueError("actor_required")
        if not content.strip():
            raise ValueError("content_empty")
        with project_authority_lock(self.project_root):
            versions = self.versions(chapter_number)
            current = versions[-1] if versions else None
            actual = None if current is None else current.version
            if expected_version != actual:
                raise DraftConflictError("version_conflict")
            version_number = 1 if current is None else current.version + 1
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            now = datetime.now(timezone.utc).isoformat()
            version = WriterVersionDTO(version_number, digest, now, actor, actual, f"draft:chapter-{chapter_number:03d}")
            self.root.mkdir(parents=True, exist_ok=True)
            with self._path(chapter_number).open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps({**self._encode(version), "content": content}, ensure_ascii=False, sort_keys=True) + "\n")
            return version

    def restore(self, chapter_number: int, version_number: int, *, actor: str, expected_version: int | None = None) -> WriterVersionDTO:
        with project_authority_lock(self.project_root):
            records = [json.loads(line) for line in self._path(chapter_number).read_text(encoding="utf-8").splitlines()] if self._path(chapter_number).exists() else []
            selected = next((item for item in records if item["version"] == version_number), None)
            if selected is None:
                raise DraftNotFoundError(version_number)
            return self.save(chapter_number, selected["content"], actor=actor, expected_version=expected_version)

    @staticmethod
    def _encode(version: WriterVersionDTO) -> dict[str, object]:
        return {"version": version.version, "content_hash": version.content_hash, "created_at": version.created_at, "actor": version.actor, "parent_version": version.parent_version, "source_key": version.source_key}

    @staticmethod
    def _decode(line: str) -> WriterVersionDTO:
        value = json.loads(line)
        return WriterVersionDTO(value["version"], value["content_hash"], value["created_at"], value["actor"], value["parent_version"], value["source_key"])

    def _path(self, chapter_number: int) -> Path:
        return self.root / f"chapter_{chapter_number:03d}.jsonl"

