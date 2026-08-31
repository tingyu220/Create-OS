"""独立小说验收样本的严格加载器。"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    NarrativeDecision,
    NarrativeProjectProfile,
    NarrativeValidationError,
)
from creative_os.domains.novel_chapter_boundary import ChapterBoundary
from creative_os.domains.novel_chapter_planner import ChapterPlanningRequest
from creative_os.domains.novel_review_model import CharacterStateProposal
from creative_os.domains.novel_writer import NovelDraft, NovelWritingRequest
from creative_os.domains.novel_writer_admission import NovelAdmissionRequest


_ROOT_FIELDS = frozenset({
    "schema_version", "profile", "planning", "current_state", "baseline_evidence",
    "writing", "boundary", "character_changes", "fake_draft",
})
_WRITING_FIELDS = frozenset({"chapter_id", "context_fingerprint", "instruction", "run_id", "source_chapter"})
_BOUNDARY_FIELDS = frozenset({
    "entry_state", "exit_state", "ending_function", "dialogue_closed",
    "dramatic_unit_closed", "estimated_chinese_chars",
})
_DRAFT_FIELDS = frozenset({"content", "content_hash"})
_CURRENT_STATE_FIELDS = frozenset({"chapter_id", "characters", "open_hooks"})
_CHARACTER_FIELDS = frozenset({"subject", "current_goal", "constraint"})
_BASELINE_EVIDENCE_FIELDS = frozenset({"source_id", "source_hash", "assertion"})
_BASELINE_POLICY_FIELDS = frozenset({"source_id", "assertion_pointer"})
_CHARACTER_CHANGE_FIELDS = frozenset({"subject", "change", "evidence"})
_MIN_CHINESE_CHARS = 2500
_SYSTEM_TERMS = ("系统", "合同", "场景", "字数", "审查", "验证", "夹具", "Fake", "JSON", "规划", "状态")


@dataclass(frozen=True, slots=True)
class FixtureBaselineEvidence:
    source_id: str
    source_hash: str
    assertion: str


@dataclass(frozen=True, slots=True)
class FixtureBaselinePolicy:
    source_id: str
    assertion_pointer: str


@dataclass(frozen=True, slots=True)
class FixtureCurrentState:
    chapter_id: str
    characters: tuple[dict[str, str], ...]
    open_hooks: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IndependentNovelValidationCase:
    profile: NarrativeProjectProfile
    planning: NarrativeDecision
    current_state: FixtureCurrentState
    baseline_evidence: tuple[FixtureBaselineEvidence, ...]
    writing: NovelWritingRequest
    admission: NovelAdmissionRequest
    boundary: ChapterBoundary
    character_changes: tuple[CharacterStateProposal, ...]
    fake_draft: NovelDraft
    source_chapter: str

    @property
    def chapter_contract(self):
        return self.planning.chapter_contract

    @property
    def planning_request(self) -> ChapterPlanningRequest:
        return ChapterPlanningRequest(scene_plan=self.chapter_contract.scene_plan, boundary=self.boundary)


def load_independent_validation_case(path: str | Path) -> IndependentNovelValidationCase:
    """加载只服务于独立短篇验收的严格 JSON 数据。"""
    fixture_path = Path(path).resolve()
    payload = _load_root(fixture_path)
    _require_exact_fields(payload, _ROOT_FIELDS, "root", unknown_label="unknown root field")
    if payload["schema_version"] != 1:
        raise NarrativeValidationError("unsupported validation fixture schema")

    profile = _load_profile(payload["profile"])
    planning = _load_planning(payload["planning"])
    if planning.profile_id != profile.id:
        raise NarrativeValidationError("planning profile identity mismatch")
    _validate_chapter_identity(planning)
    _validate_scene_contract(planning)

    project_root = fixture_path.parent.parent
    current_state = _load_current_state(payload["current_state"], planning.chapter_contract.chapter_id)
    baseline_policy = _load_baseline_policy(project_root)
    baseline_evidence = _load_baseline_evidence(
        payload["baseline_evidence"], project_root, baseline_policy,
    )
    writing, admission, source_chapter = _load_writing(payload["writing"], planning)
    boundary = _load_boundary(payload["boundary"])
    if boundary.estimated_chinese_chars < _MIN_CHINESE_CHARS:
        raise NarrativeValidationError("boundary minimum chinese chars not met")
    character_changes = _load_character_changes(payload["character_changes"])
    fake_draft = _load_fake_draft(payload["fake_draft"], boundary, planning)

    return IndependentNovelValidationCase(
        profile=profile,
        planning=planning,
        current_state=current_state,
        baseline_evidence=baseline_evidence,
        writing=writing,
        admission=admission,
        boundary=boundary,
        character_changes=character_changes,
        fake_draft=fake_draft,
        source_chapter=source_chapter,
    )


def _load_root(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NarrativeValidationError("validation fixture must be valid JSON") from error
    return _object(payload, "root")


def _load_profile(value: object) -> NarrativeProjectProfile:
    payload = _object(value, "profile")
    _require_exact_fields(payload, {"id", "story_contract", "volumes", "arcs"}, "profile")
    profile = NarrativeProjectProfile.from_json(json.dumps(payload, ensure_ascii=False))
    profile.validate()
    return profile


def _load_planning(value: object) -> NarrativeDecision:
    payload = _object(value, "planning")
    if "chapter_contract" not in payload:
        raise NarrativeValidationError("chapter identity requires chapter_contract")
    try:
        return NarrativeDecisionCodec.decode_v2(payload)
    except NarrativeValidationError:
        raise
    except (TypeError, ValueError) as error:
        raise NarrativeValidationError("invalid planning") from error


def _validate_chapter_identity(planning: NarrativeDecision) -> None:
    contract = planning.chapter_contract
    if not contract.chapter_id or contract.chapter_id != f"chapter_{planning.chapter:03d}":
        raise NarrativeValidationError("chapter identity mismatch")
    if planning.contract_id != f"narrative-chapter-{planning.chapter:03d}":
        raise NarrativeValidationError("chapter identity mismatch")


def _validate_scene_contract(planning: NarrativeDecision) -> None:
    scenes = planning.chapter_contract.scene_plan.scenes
    if not scenes:
        raise NarrativeValidationError("empty scene plan")
    try:
        planning.chapter_contract.scene_plan.validate(required=True, novel_required=True)
    except NarrativeValidationError as error:
        if "closure" in str(error):
            raise NarrativeValidationError("scene closure incomplete") from error
        raise


def _load_current_state(value: object, chapter_id: str) -> FixtureCurrentState:
    payload = _object(value, "current_state")
    _require_exact_fields(payload, _CURRENT_STATE_FIELDS, "current_state")
    if _text(payload["chapter_id"], "current_state.chapter_id") != chapter_id:
        raise NarrativeValidationError("current_state chapter identity mismatch")
    characters: list[dict[str, str]] = []
    for item in _objects(payload["characters"], "current_state.characters"):
        _require_exact_fields(item, _CHARACTER_FIELDS, "current_state character")
        characters.append({key: _text(item[key], f"current_state character {key}") for key in _CHARACTER_FIELDS})
    if not characters:
        raise NarrativeValidationError("current_state characters required")
    return FixtureCurrentState(
        chapter_id=chapter_id,
        characters=tuple(characters),
        open_hooks=_strings(payload["open_hooks"], "current_state.open_hooks"),
    )


def _load_baseline_evidence(
    value: object, project_root: Path, policy: FixtureBaselinePolicy,
) -> tuple[FixtureBaselineEvidence, ...]:
    result: list[FixtureBaselineEvidence] = []
    for item in _objects(value, "baseline_evidence"):
        _require_exact_fields(item, _BASELINE_EVIDENCE_FIELDS, "baseline_evidence item")
        source_id = _text(item["source_id"], "baseline_evidence.source_id")
        source_hash = _text(item["source_hash"], "baseline_evidence.source_hash")
        if len(source_hash) != 64 or any(char not in "0123456789abcdef" for char in source_hash):
            raise NarrativeValidationError("baseline evidence source_hash invalid")
        source_path = _resolve_baseline_source(project_root, source_id)
        if source_id != policy.source_id:
            raise NarrativeValidationError("baseline evidence source binding mismatch")
        actual_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if actual_hash != source_hash:
            raise NarrativeValidationError("baseline evidence source hash mismatch")
        assertion = _text(item["assertion"], "baseline_evidence.assertion")
        if assertion != _read_baseline_assertion(source_path, policy.assertion_pointer):
            raise NarrativeValidationError("baseline evidence assertion mismatch")
        result.append(FixtureBaselineEvidence(
            source_id=source_id,
            source_hash=source_hash,
            assertion=assertion,
        ))
    if not result:
        raise NarrativeValidationError("baseline evidence required")
    return tuple(result)


def _load_baseline_policy(project_root: Path) -> FixtureBaselinePolicy:
    project_path = project_root / "project.json"
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NarrativeValidationError("validation project metadata invalid") from error
    payload = _object(project, "validation project metadata")
    policy = _object(payload.get("validation_baseline"), "validation_baseline")
    _require_exact_fields(policy, _BASELINE_POLICY_FIELDS, "validation_baseline")
    source_id = _text(policy["source_id"], "validation_baseline.source_id")
    assertion_pointer = _text(
        policy["assertion_pointer"], "validation_baseline.assertion_pointer",
    )
    _resolve_baseline_source(project_root, source_id)
    return FixtureBaselinePolicy(source_id, assertion_pointer)


def _read_baseline_assertion(source_path: Path, pointer: str) -> str:
    """按项目元数据声明的 JSON Pointer 读取可审计断言。"""
    try:
        value: object = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NarrativeValidationError("baseline evidence assertion source invalid") from error
    if not pointer.startswith("/"):
        raise NarrativeValidationError("baseline evidence assertion pointer invalid")
    for token in pointer.removeprefix("/").split("/"):
        key = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdecimal() and int(key) < len(value):
            value = value[int(key)]
        else:
            raise NarrativeValidationError("baseline evidence assertion pointer invalid")
    return _text(value, "baseline evidence assertion source")


def _resolve_baseline_source(project_root: Path, source_id: str) -> Path:
    """解析项目内来源文件，拒绝绝对路径、穿越路径及符号链接逃逸。"""
    source_path = Path(source_id)
    if source_path.is_absolute() or ".." in source_path.parts:
        raise NarrativeValidationError("baseline evidence source path outside project")
    candidate = (project_root / source_path).resolve()
    try:
        candidate.relative_to(project_root)
    except ValueError as error:
        raise NarrativeValidationError("baseline evidence source path outside project") from error
    if not candidate.is_file():
        raise NarrativeValidationError("baseline evidence source unavailable")
    return candidate


def _load_writing(value: object, planning: NarrativeDecision) -> tuple[NovelWritingRequest, NovelAdmissionRequest, str]:
    payload = _object(value, "writing")
    _require_exact_fields(payload, _WRITING_FIELDS, "writing")
    chapter_id = _text(payload["chapter_id"], "writing.chapter_id")
    if chapter_id != planning.chapter_contract.chapter_id:
        raise NarrativeValidationError("writing chapter identity mismatch")
    fingerprint = _hash(payload["context_fingerprint"], "writing.context_fingerprint")
    run_id = _text(payload["run_id"], "writing.run_id")
    source_chapter = _text(payload["source_chapter"], "writing.source_chapter")
    return (
        NovelWritingRequest.from_narrative_decision(
            planning,
            context_fingerprint=fingerprint,
            instruction=_text(payload["instruction"], "writing.instruction"),
        ),
        NovelAdmissionRequest(planning.contract_id, fingerprint, run_id),
        source_chapter,
    )


def _load_boundary(value: object) -> ChapterBoundary:
    payload = _object(value, "boundary")
    _require_exact_fields(payload, _BOUNDARY_FIELDS, "boundary")
    boundary = ChapterBoundary(
        entry_state=_text(payload["entry_state"], "boundary.entry_state"),
        exit_state=_text(payload["exit_state"], "boundary.exit_state"),
        ending_function=_text(payload["ending_function"], "boundary.ending_function"),
        dialogue_closed=_bool(payload["dialogue_closed"], "boundary.dialogue_closed"),
        dramatic_unit_closed=_bool(payload["dramatic_unit_closed"], "boundary.dramatic_unit_closed"),
        estimated_chinese_chars=_integer(payload["estimated_chinese_chars"], "boundary.estimated_chinese_chars"),
    )
    try:
        boundary.validate()
    except ValueError as error:
        raise NarrativeValidationError(str(error)) from error
    return boundary


def _load_character_changes(value: object) -> tuple[CharacterStateProposal, ...]:
    changes: list[CharacterStateProposal] = []
    for item in _objects(value, "character_changes"):
        _require_exact_fields(item, _CHARACTER_CHANGE_FIELDS, "character_change")
        change = CharacterStateProposal(
            subject=_text(item["subject"], "character_change.subject"),
            change=_text(item["change"], "character_change.change"),
            evidence=_strings(item["evidence"], "character_change.evidence"),
        )
        change.validate()
        changes.append(change)
    if not changes:
        raise NarrativeValidationError("character changes required")
    return tuple(changes)


def _load_fake_draft(value: object, boundary: ChapterBoundary, planning: NarrativeDecision) -> NovelDraft:
    payload = _object(value, "fake_draft")
    _require_exact_fields(payload, _DRAFT_FIELDS, "fake_draft")
    content = _text(payload["content"], "fake_draft.content")
    if any(term in content for term in _SYSTEM_TERMS):
        raise NarrativeValidationError("fake draft contains system terminology")
    expected_hash = _hash(payload["content_hash"], "fake_draft.content_hash")
    draft = NovelDraft.from_content(content)
    if draft.content_hash != expected_hash:
        raise NarrativeValidationError("fake draft content hash mismatch")
    if _chinese_char_count(content) < boundary.estimated_chinese_chars:
        raise NarrativeValidationError("fake draft below boundary minimum")
    for scene in planning.chapter_contract.scene_plan.scenes:
        for information in scene.essential_information:
            if information not in content:
                raise NarrativeValidationError("fake draft essential information missing")
    return draft


def _require_exact_fields(payload: Mapping[str, Any], expected: set[str] | frozenset[str], name: str, *, unknown_label: str | None = None) -> None:
    actual = set(payload)
    missing = set(expected) - actual
    unexpected = actual - set(expected)
    if missing:
        raise NarrativeValidationError(f"{name} missing field: {sorted(missing)[0]}")
    if unexpected:
        label = unknown_label or f"{name} unknown field"
        raise NarrativeValidationError(f"{label}: {sorted(unexpected)[0]}")


def _object(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NarrativeValidationError(f"{name} must be object")
    return value


def _objects(value: object, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise NarrativeValidationError(f"{name} must be list")
    return [_object(item, name) for item in value]


def _strings(value: object, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise NarrativeValidationError(f"{name} requires non-empty strings")
    return tuple(_text(item, name) for item in value)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NarrativeValidationError(f"{name} is required")
    return value


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise NarrativeValidationError(f"{name} must be integer")
    return value


def _bool(value: object, name: str) -> bool:
    if type(value) is not bool:
        raise NarrativeValidationError(f"{name} must be bool")
    return value


def _hash(value: object, name: str) -> str:
    content_hash = _text(value, name)
    if len(content_hash) != 64 or any(char not in "0123456789abcdef" for char in content_hash):
        raise NarrativeValidationError(f"{name} must be SHA-256")
    return content_hash


def _chinese_char_count(content: str) -> int:
    return sum("\u4e00" <= char <= "\u9fff" for char in content)
