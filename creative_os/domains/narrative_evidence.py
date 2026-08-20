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


class EvidenceSourceKind(StrEnum):
    TASK = "task"
    DIRECTOR = "director"
    PROFILE = "profile"
    FACT_SNAPSHOT = "fact_snapshot"
    PREVIOUS_CHAPTER = "previous_chapter"
    OUTLINE_CHANGE = "outline_change"


EvidenceValue = str | int | bool


_LOCATOR_KINDS = frozenset({"json_pointer", "line_range", "text_anchor", "record_id"})


def _require_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")


def _require_evidence_value(value: object, name: str) -> None:
    if isinstance(value, str):
        _require_text(value, name)
        return
    if type(value) in (int, bool):
        return
    raise ValueError(f"{name} must be a scalar evidence value")


def _same_evidence_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


@dataclass(frozen=True, slots=True)
class EvidenceLocator:
    kind: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in _LOCATOR_KINDS:
            raise ValueError(f"unsupported evidence locator kind: {self.kind}")
        _require_text(self.value, "locator value")


@dataclass(frozen=True, slots=True)
class EvidenceAssertion:
    field_path: str
    value: EvidenceValue

    def __post_init__(self) -> None:
        _require_text(self.field_path, "assertion field_path")
        _require_evidence_value(self.value, "asserted value")


@dataclass(frozen=True, slots=True, init=False)
class EvidenceRef:
    """The single immutable evidence type for contracts and legacy replay reads."""

    source_type: str | None
    source_ref: str | None
    excerpt: str
    evidence_id: str | None
    contract_id: str | None
    contract_version: int | None
    field_path: str | None
    role: EvidenceRole | None
    source_id: str | None
    source_version: str | None
    source_content_hash: str | None
    locator: EvidenceLocator | None
    assertion: str | None
    asserted_value: EvidenceValue | None

    def __init__(
        self,
        source_type: str | None = None,
        source_ref: str | None = None,
        excerpt: str | None = None,
        *,
        evidence_id: str | None = None,
        contract_id: str | None = None,
        contract_version: int | None = None,
        field_path: str | None = None,
        role: EvidenceRole | None = None,
        source_id: str | None = None,
        source_version: str | None = None,
        source_content_hash: str | None = None,
        locator: EvidenceLocator | None = None,
        assertion: str | None = None,
        asserted_value: EvidenceValue | None = None,
    ) -> None:
        legacy_values = (source_type, source_ref)
        field_values = (
            evidence_id,
            contract_id,
            contract_version,
            field_path,
            role,
            source_id,
            source_version,
            source_content_hash,
            locator,
            assertion,
            asserted_value,
        )
        if any(value is not None for value in legacy_values):
            if any(value is not None for value in field_values):
                raise ValueError("legacy replay evidence cannot include contract binding fields")
            _require_text(source_type, "source_type")
            _require_text(source_ref, "source_ref")
            _require_text(excerpt, "excerpt")
            object.__setattr__(self, "source_type", source_type)
            object.__setattr__(self, "source_ref", source_ref)
            object.__setattr__(self, "excerpt", excerpt)
            for name in (
                "evidence_id",
                "contract_id",
                "contract_version",
                "field_path",
                "role",
                "source_id",
                "source_version",
                "source_content_hash",
                "locator",
                "assertion",
                "asserted_value",
            ):
                object.__setattr__(self, name, None)
            return

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
            _require_text(locals()[name], name)
        if type(contract_version) is not int or contract_version < 1:
            raise ValueError("contract_version must be a positive integer")
        if not isinstance(role, EvidenceRole):
            raise ValueError("role must be an EvidenceRole")
        if not isinstance(locator, EvidenceLocator):
            raise ValueError("locator must be an EvidenceLocator")
        if asserted_value is not None:
            _require_evidence_value(asserted_value, "asserted_value")
        object.__setattr__(self, "source_type", None)
        object.__setattr__(self, "source_ref", None)
        object.__setattr__(self, "excerpt", excerpt)
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "contract_id", contract_id)
        object.__setattr__(self, "contract_version", contract_version)
        object.__setattr__(self, "field_path", field_path)
        object.__setattr__(self, "role", role)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "source_version", source_version)
        object.__setattr__(self, "source_content_hash", source_content_hash)
        object.__setattr__(self, "locator", locator)
        object.__setattr__(self, "assertion", assertion)
        object.__setattr__(self, "asserted_value", asserted_value)

    @property
    def is_legacy_replay_ref(self) -> bool:
        return self.source_type is not None

    def validate(self) -> None:
        if self.is_legacy_replay_ref:
            _require_text(self.source_type, "source_type")
            _require_text(self.source_ref, "source_ref")
            _require_text(self.excerpt, "excerpt")
            return
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
        if type(self.contract_version) is not int or self.contract_version < 1:
            raise ValueError("contract_version must be a positive integer")
        if not isinstance(self.role, EvidenceRole):
            raise ValueError("role must be an EvidenceRole")
        if not isinstance(self.locator, EvidenceLocator):
            raise ValueError("locator must be an EvidenceLocator")
        if self.asserted_value is not None:
            _require_evidence_value(self.asserted_value, "asserted_value")

    @property
    def deduplication_key(self) -> tuple[str, int, str, EvidenceRole, str, str, EvidenceLocator, str]:
        if self.is_legacy_replay_ref:
            raise ValueError("legacy replay evidence has no contract deduplication key")
        assert self.contract_id is not None
        assert self.contract_version is not None
        assert self.field_path is not None
        assert self.role is not None
        assert self.source_id is not None
        assert self.source_version is not None
        assert self.locator is not None
        assert self.source_content_hash is not None
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
    source_kind: EvidenceSourceKind | None = None
    asserted_values: tuple[EvidenceAssertion, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.source_version, "source_version")
        _require_text(self.source_content_hash, "source_content_hash")
        if self.source_kind is not None and not isinstance(self.source_kind, EvidenceSourceKind):
            raise ValueError("source_kind must be an EvidenceSourceKind")
        if (
            not isinstance(self.located_excerpts, tuple)
            or not isinstance(self.assertions_by_field_path, tuple)
            or not isinstance(self.asserted_values, tuple)
        ):
            raise ValueError("resolved evidence source collections must be tuples")
        for item in self.located_excerpts:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("located_excerpts entries must be tuples")
            locator, excerpt = item
            if not isinstance(locator, EvidenceLocator):
                raise ValueError("located_excerpts requires EvidenceLocator values")
            _require_text(excerpt, "located excerpt")
        for item in self.assertions_by_field_path:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("assertion entries must be tuples")
            field_path, assertions = item
            _require_text(field_path, "assertion field_path")
            if not isinstance(assertions, tuple):
                raise ValueError("assertions must be tuples")
            if not assertions or any(not isinstance(value, str) or not value.strip() for value in assertions):
                raise ValueError("assertions must contain non-empty values")
        seen_asserted_paths: set[str] = set()
        for assertion in self.asserted_values:
            if not isinstance(assertion, EvidenceAssertion):
                raise ValueError("asserted_values must contain EvidenceAssertion values")
            if assertion.field_path in seen_asserted_paths:
                raise ValueError("asserted_values field paths must be unique")
            seen_asserted_paths.add(assertion.field_path)

    def excerpt_at(self, locator: EvidenceLocator) -> str | None:
        for candidate, excerpt in self.located_excerpts:
            if candidate == locator:
                return excerpt
        return None

    def supports_assertion(self, field_path: str, assertion: str) -> bool:
        return any(path == field_path and assertion in assertions for path, assertions in self.assertions_by_field_path)

    def asserted_value_at(self, field_path: str) -> EvidenceValue | None:
        for assertion in self.asserted_values:
            if assertion.field_path == field_path:
                return assertion.value
        return None


SourceResolver = Callable[[str], ResolvedEvidenceSource | None]


@dataclass(frozen=True, slots=True)
class EvidenceValidationResult:
    source: ResolvedEvidenceSource | None
    issues: tuple[ContractIssue, ...]


_EXPECTED_VALUE_UNSET = object()


class EvidenceIntegrityValidator:
    """Fail-closed validator for a single field-level EvidenceRef."""

    def __init__(self, source_resolver: SourceResolver) -> None:
        self._source_resolver = source_resolver

    def validate(
        self,
        ref: object,
        expected_field_path: str,
        *,
        expected_value: object = _EXPECTED_VALUE_UNSET,
        require_source_kind: bool = False,
    ) -> tuple[ContractIssue, ...]:
        return self.validate_resolved(
            ref,
            expected_field_path,
            expected_value=expected_value,
            require_source_kind=require_source_kind,
        ).issues

    def validate_resolved(
        self,
        ref: object,
        expected_field_path: str,
        *,
        expected_value: object = _EXPECTED_VALUE_UNSET,
        require_source_kind: bool = False,
    ) -> EvidenceValidationResult:
        if not isinstance(ref, EvidenceRef):
            return EvidenceValidationResult(
                None,
                (self._issue("evidence_ref_required", expected_field_path, "请提供字段级 EvidenceRef，而不是存储信封证据。"),),
            )
        if ref.is_legacy_replay_ref or ref.field_path != expected_field_path:
            return EvidenceValidationResult(
                None,
                (self._issue("evidence_field_path_mismatch", expected_field_path, "将证据绑定到当前字段路径。"),),
            )
        try:
            source = self._source_resolver(ref.source_id)
            if source is None:
                return EvidenceValidationResult(
                    None,
                    (self._issue("evidence_source_missing", ref.field_path, "恢复来源或重新绑定证据。"),),
                )
            if source.source_id != ref.source_id:
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_source_mismatch", ref.field_path, "重新绑定正确的来源。"),),
                )
            if source.source_version != ref.source_version:
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_version_mismatch", ref.field_path, "更新为来源的当前版本。"),),
                )
            if source.source_content_hash != ref.source_content_hash:
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_hash_mismatch", ref.field_path, "更新为来源的当前内容哈希。"),),
                )
            if require_source_kind and not isinstance(source.source_kind, EvidenceSourceKind):
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_source_kind_missing", ref.field_path, "为权威来源声明严格 producer kind。"),),
                )
            authoritative_excerpt = source.excerpt_at(ref.locator)
            if authoritative_excerpt is None:
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_locator_unresolved", ref.field_path, "使用当前来源中可定位的位置。"),),
                )
            if authoritative_excerpt != ref.excerpt:
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_excerpt_mismatch", ref.field_path, "使用 locator 返回的权威内容。"),),
                )
            if not source.supports_assertion(ref.field_path, ref.assertion):
                return EvidenceValidationResult(
                    source,
                    (self._issue("evidence_assertion_mismatch", ref.field_path, "为该字段提供可验证的断言。"),),
                )
            if expected_value is not _EXPECTED_VALUE_UNSET:
                authoritative_value = source.asserted_value_at(ref.field_path)
                if not _same_evidence_value(
                    ref.asserted_value,
                    expected_value,
                ) or not _same_evidence_value(authoritative_value, expected_value):
                    return EvidenceValidationResult(
                        source,
                        (
                            self._issue(
                                "evidence_asserted_value_mismatch",
                                ref.field_path,
                                "将结构化断言值绑定到候选的实际字段值。",
                            ),
                        ),
                    )
        except Exception:
            return EvidenceValidationResult(
                None,
                (self._issue("evidence_source_unavailable", ref.field_path, "恢复可读取的权威来源后重新校验。"),),
            )
        return EvidenceValidationResult(source, ())

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
