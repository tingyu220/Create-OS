from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Callable

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck


class EvidenceRole(StrEnum):
    INTENT = "intent"
    VERIFICATION = "verification"
    REALIZATION = "realization"
    NON_APPLICABILITY = "non_applicability"
    DECISION = "decision"


_LOCATOR_KINDS = frozenset({"json_pointer", "line_range", "text_anchor", "record_id"})


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in _LOCATOR_KINDS:
            raise ValueError(f"unsupported evidence locator kind: {self.kind}")
        _require_text(self.value, "locator value")


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    """Immutable evidence bound to one contract field and one source version."""

    evidence_id: str
    contract_id: str
    contract_version: int
    field_path: str
    role: EvidenceRole
    source_id: str
    source_version: str
    source_content_hash: str
    locator: EvidenceLocator
    excerpt: str
    assertion: str

    def __post_init__(self) -> None:
        for name in (
            "evidence_id",
            "contract_id",
            "field_path",
            "source_id",
            "source_version",
            "source_content_hash",
            "excerpt",
            "assertion",
        ):
            _require_text(getattr(self, name), name)
        if not isinstance(self.contract_version, int) or self.contract_version < 1:
            raise ValueError("contract_version must be a positive integer")
        if not isinstance(self.role, EvidenceRole):
            raise ValueError("role must be an EvidenceRole")
        if not isinstance(self.locator, EvidenceLocator):
            raise ValueError("locator must be an EvidenceLocator")

    @property
    def deduplication_key(self) -> tuple[str, int, str, EvidenceRole, str, str, EvidenceLocator, str]:
        return (
            self.contract_id,
            self.contract_version,
            self.field_path,
            self.role,
            self.source_id,
            self.source_version,
            self.locator,
            self.source_content_hash,
        )


def deduplicate_evidence_refs(values: tuple[EvidenceRef, ...] | list[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    """Keep the first ref for each contract evidence eight-tuple."""

    result: list[EvidenceRef] = []
    seen: set[tuple[str, int, str, EvidenceRole, str, str, EvidenceLocator, str]] = set()
    for value in values:
        if not isinstance(value, EvidenceRef):
            raise ValueError("field evidence must use EvidenceRef")
        if value.deduplication_key not in seen:
            seen.add(value.deduplication_key)
            result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ResolvedEvidenceSource:
    """Authoritative source snapshot supplied by an injected resolver."""

    source_id: str
    source_version: str
    source_content_hash: str
    located_excerpts: tuple[tuple[EvidenceLocator, str], ...]
    assertions_by_field_path: tuple[tuple[str, tuple[str, ...]], ...]

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.source_version, "source_version")
        _require_text(self.source_content_hash, "source_content_hash")
        for locator, excerpt in self.located_excerpts:
            if not isinstance(locator, EvidenceLocator):
                raise ValueError("located_excerpts requires EvidenceLocator values")
            _require_text(excerpt, "located excerpt")
        for field_path, assertions in self.assertions_by_field_path:
            _require_text(field_path, "assertion field_path")
            if not assertions or any(not isinstance(value, str) or not value.strip() for value in assertions):
                raise ValueError("assertions must contain non-empty values")

    def excerpt_at(self, locator: EvidenceLocator) -> str | None:
        for candidate, excerpt in self.located_excerpts:
            if candidate == locator:
                return excerpt
        return None

    def supports_assertion(self, field_path: str, assertion: str) -> bool:
        return any(path == field_path and assertion in assertions for path, assertions in self.assertions_by_field_path)


SourceResolver = Callable[[str], ResolvedEvidenceSource | None]


class EvidenceIntegrityValidator:
    """Fail-closed validator for a single field-level EvidenceRef."""

    def __init__(self, source_resolver: SourceResolver) -> None:
        self._source_resolver = source_resolver

    def validate(self, ref: object, expected_field_path: str) -> tuple[ContractIssue, ...]:
        if not isinstance(ref, EvidenceRef):
            return (self._issue("evidence_ref_required", expected_field_path, "请提供字段级 EvidenceRef，而不是存储信封证据。"),)
        if ref.field_path != expected_field_path:
            return (self._issue("evidence_field_path_mismatch", expected_field_path, "将证据绑定到当前字段路径。"),)
        try:
            source = self._source_resolver(ref.source_id)
        except Exception:
            return (self._issue("evidence_source_unavailable", ref.field_path, "恢复可读取的权威来源后重新校验。"),)
        if source is None:
            return (self._issue("evidence_source_missing", ref.field_path, "恢复来源或重新绑定证据。"),)
        if source.source_id != ref.source_id:
            return (self._issue("evidence_source_mismatch", ref.field_path, "重新绑定正确的来源。"),)
        if source.source_version != ref.source_version:
            return (self._issue("evidence_version_mismatch", ref.field_path, "更新为来源的当前版本。"),)
        if source.source_content_hash != ref.source_content_hash:
            return (self._issue("evidence_hash_mismatch", ref.field_path, "更新为来源的当前内容哈希。"),)
        if source.excerpt_at(ref.locator) is None:
            return (self._issue("evidence_locator_unresolved", ref.field_path, "使用当前来源中可定位的位置。"),)
        if not source.supports_assertion(ref.field_path, ref.assertion):
            return (self._issue("evidence_assertion_mismatch", ref.field_path, "为该字段提供可验证的断言。"),)
        return ()

    @staticmethod
    def _issue(code: str, field_path: str, repair_hint: str) -> ContractIssue:
        return ContractIssue(
            code=code,
            severity="error",
            blocking=True,
            field_path=field_path,
            evidence_checks=(EvidenceCheck(code=code, passed=False, detail=repair_hint),),
            repair_hint=repair_hint,
        )


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
