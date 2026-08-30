from __future__ import annotations

from dataclasses import dataclass


NOVEL_CAPABILITY_NAMES = (
    "chapter_planning",
    "writer_admission",
    "draft_writing",
    "draft_review",
    "approved_compile",
    "lesson_candidate",
)


@dataclass(frozen=True, slots=True)
class NovelCapabilityCatalog:
    """Novel Domain 对外承诺的可执行能力目录。"""

    names: tuple[str, ...] = NOVEL_CAPABILITY_NAMES

    def __post_init__(self) -> None:
        if not self.names or any(not name.strip() for name in self.names):
            raise ValueError("novel_capability_name_invalid")
        if len(self.names) != len(set(self.names)):
            raise ValueError("novel_capability_name_duplicate")
