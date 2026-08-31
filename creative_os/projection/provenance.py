from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_ABSOLUTE_PATTERN = re.compile(r"^[A-Za-z]:[\\/]")


def _required(value: str, code: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(code)
    return normalized


def _content_hash(value: str | None, code: str) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not _SHA256_PATTERN.fullmatch(normalized):
        raise ValueError(code)
    return normalized


@dataclass(frozen=True, slots=True)
class SourceRef:
    source_kind: str
    source_id: str
    locator: str
    content_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", _required(self.source_kind, "source_kind_required"))
        object.__setattr__(self, "source_id", _required(self.source_id, "source_id_required"))
        locator = self.locator.strip().replace("\\", "/")
        path = PurePosixPath(locator)
        if (
            not locator
            or locator.startswith("/")
            or locator.startswith("//")
            or _WINDOWS_ABSOLUTE_PATTERN.match(self.locator.strip())
            or ".." in path.parts
        ):
            raise ValueError("source_locator_must_be_project_relative")
        object.__setattr__(self, "locator", path.as_posix())
        object.__setattr__(self, "content_hash", _content_hash(self.content_hash, "source_content_hash_invalid"))


@dataclass(frozen=True, slots=True)
class SourceHead:
    source_kind: str
    source_id: str
    cursor: str | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_kind", _required(self.source_kind, "source_kind_required"))
        object.__setattr__(self, "source_id", _required(self.source_id, "source_id_required"))
        cursor = self.cursor.strip() if self.cursor is not None else None
        if cursor == "":
            cursor = None
        content_hash = _content_hash(self.content_hash, "source_head_content_hash_invalid")
        if cursor is None and content_hash is None:
            raise ValueError("source_head_position_required")
        object.__setattr__(self, "cursor", cursor)
        object.__setattr__(self, "content_hash", content_hash)


@dataclass(frozen=True, slots=True)
class Derivation:
    rule_id: str
    inputs: tuple[SourceRef, ...]
    explanation: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _required(self.rule_id, "derivation_rule_id_required"))
        if not self.inputs:
            raise ValueError("derivation_inputs_required")
        if any(not isinstance(item, SourceRef) for item in self.inputs):
            raise TypeError("derivation_inputs_invalid")
        object.__setattr__(self, "explanation", self.explanation.strip())
