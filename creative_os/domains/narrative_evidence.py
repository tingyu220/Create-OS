from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class JsonArtifact:
    source_ref: str
    data: dict[str, object]


@dataclass(frozen=True, slots=True)
class TextArtifact:
    source_ref: str
    content: str


@dataclass(frozen=True, slots=True)
class ChapterEvidence:
    chapter_id: str
    prose: str
    contexts: tuple[JsonArtifact, ...]
    reviews: tuple[TextArtifact, ...]
    knowledge: tuple[JsonArtifact, ...]
    tasks: tuple[JsonArtifact, ...]
    source_refs: tuple[str, ...]

    def source_paths(self) -> tuple[Path, ...]:
        return tuple(Path(source_ref) for source_ref in self.source_refs)


def load_chapter_evidence(project_root: str | Path, chapter_number: int) -> ChapterEvidence:
    if chapter_number < 1:
        raise ValueError("chapter_number must be positive")
    root = Path(project_root)
    chapter_id = f"chapter_{chapter_number:03d}"
    prose_path = root / "production" / "final_chapters" / f"{chapter_id}.md"
    if not prose_path.is_file():
        raise FileNotFoundError(f"missing canonical chapter: {chapter_id}")

    chapter_root = root / "production" / chapter_id
    contexts = _read_json_files(root, chapter_root / "contexts")
    reviews = _read_text_files(root, chapter_root / "reviews")
    knowledge = _read_json_files(root, chapter_root / "knowledge")
    tasks = _read_json_files(root, chapter_root / "tasks")
    source_refs = (
        _relative_ref(root, prose_path),
        *(item.source_ref for item in contexts),
        *(item.source_ref for item in reviews),
        *(item.source_ref for item in knowledge),
        *(item.source_ref for item in tasks),
    )
    return ChapterEvidence(
        chapter_id=chapter_id,
        prose=prose_path.read_text(encoding="utf-8"),
        contexts=contexts,
        reviews=reviews,
        knowledge=knowledge,
        tasks=tasks,
        source_refs=source_refs,
    )


def _read_json_files(root: Path, directory: Path) -> tuple[JsonArtifact, ...]:
    if not directory.is_dir():
        return ()
    artifacts: list[JsonArtifact] = []
    for path in sorted((item for item in directory.iterdir() if item.is_file()), key=lambda item: item.name):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON artifact: {path}") from error
        if not isinstance(data, dict):
            raise ValueError(f"JSON artifact root must be an object: {path}")
        artifacts.append(JsonArtifact(source_ref=_relative_ref(root, path), data=data))
    return tuple(artifacts)


def _read_text_files(root: Path, directory: Path) -> tuple[TextArtifact, ...]:
    if not directory.is_dir():
        return ()
    return tuple(
        TextArtifact(source_ref=_relative_ref(root, path), content=path.read_text(encoding="utf-8"))
        for path in sorted((item for item in directory.iterdir() if item.is_file()), key=lambda item: item.name)
    )


def _relative_ref(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
