import json
import ast
from pathlib import Path

import pytest

from creative_os.domains.narrative_evidence import (
    EvidenceAssertion,
    EvidenceIntegrityValidator,
    EvidenceLocator,
    EvidenceRef,
    EvidenceRole,
    EvidenceSourceKind,
    ResolvedEvidenceSource,
    deduplicate_evidence_refs,
    load_chapter_evidence,
)
from creative_os.domains.narrative_replay_model import EvidenceRef as ReplayEvidenceRef


def _seed_chapter_artifacts(root, chapter_number=1):
    chapter_id = f"chapter_{chapter_number:03d}"
    chapter_root = root / "production" / chapter_id
    final_path = root / "production" / "final_chapters" / f"{chapter_id}.md"
    final_path.parent.mkdir(parents=True)
    final_path.write_text("# 第一章\n\n主角回到了城里。\n", encoding="utf-8")

    for directory in ("contexts", "knowledge", "tasks"):
        path = chapter_root / directory
        path.mkdir(parents=True)
        (path / "b.json").write_text(json.dumps({"order": 2}), encoding="utf-8")
        (path / "a.json").write_text(json.dumps({"order": 1}), encoding="utf-8")
    reviews = chapter_root / "reviews"
    reviews.mkdir(parents=True)
    (reviews / "review.md").write_text("Pass", encoding="utf-8")
    return root


def test_load_chapter_evidence_reads_canonical_artifacts_in_stable_order(tmp_path):
    root = _seed_chapter_artifacts(tmp_path)

    evidence = load_chapter_evidence(root, 1)

    assert evidence.chapter_id == "chapter_001"
    assert "主角" in evidence.prose
    assert evidence.source_refs[0].endswith("chapter_001.md")
    assert [item.data["order"] for item in evidence.contexts] == [1, 2]
    assert len(evidence.tasks) == 2
    assert all(not path.is_absolute() for path in evidence.source_paths())


def test_load_chapter_evidence_fails_when_canonical_chapter_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="chapter_001"):
        load_chapter_evidence(tmp_path, 1)


def test_load_chapter_evidence_reports_invalid_json_path(tmp_path):
    root = _seed_chapter_artifacts(tmp_path)
    invalid = root / "production/chapter_001/contexts/a.json"
    invalid.write_text("{broken", encoding="utf-8")

    with pytest.raises(ValueError, match=r"contexts[\\/]a\.json"):
        load_chapter_evidence(root, 1)


def _evidence_ref(*, field_path="chapter_contract.functions[0]", **changes):
    values = {
        "evidence_id": "ev-001",
        "contract_id": "narrative-chapter-007",
        "contract_version": 2,
        "field_path": field_path,
        "role": EvidenceRole.INTENT,
        "source_id": "production/chapter_007/contexts/director.json",
        "source_version": "v1",
        "source_content_hash": "a" * 64,
        "locator": EvidenceLocator(kind="json_pointer", value="/functions/0"),
        "excerpt": "本章用于升级冲突。",
        "assertion": "该字段定义本章叙事功能。",
        "asserted_value": "推进主线",
    }
    values.update(changes)
    return EvidenceRef(**values)


def _resolved_source(**changes):
    values = {
        "source_id": "production/chapter_007/contexts/director.json",
        "source_version": "v1",
        "source_content_hash": "a" * 64,
        "source_kind": EvidenceSourceKind.DIRECTOR,
        "located_excerpts": ((EvidenceLocator(kind="json_pointer", value="/functions/0"), "本章用于升级冲突。"),),
        "assertions_by_field_path": (("chapter_contract.functions[0]", ("该字段定义本章叙事功能。",)),),
        "asserted_values": (EvidenceAssertion("chapter_contract.functions[0]", "推进主线"),),
    }
    values.update(changes)
    return ResolvedEvidenceSource(**values)


def test_evidence_roles_are_limited_to_the_five_contract_roles():
    assert {role.value for role in EvidenceRole} == {
        "intent",
        "verification",
        "realization",
        "non_applicability",
        "decision",
    }


def test_evidence_locator_only_accepts_design_kinds():
    with pytest.raises(ValueError, match="kind"):
        EvidenceLocator(kind="page", value="1")


def test_evidence_ref_constructor_rejects_bool_contract_version():
    with pytest.raises(ValueError, match="positive integer"):
        _evidence_ref(contract_version=True)


def test_evidence_ref_validate_rejects_bool_contract_version_defensively():
    evidence = _evidence_ref()
    object.__setattr__(evidence, "contract_version", True)

    with pytest.raises(ValueError, match="positive integer"):
        evidence.validate()


def test_evidence_deduplication_uses_contract_eight_tuple_not_excerpt():
    original = _evidence_ref()
    same_binding = _evidence_ref(evidence_id="ev-002", excerpt="相同绑定的不同摘录")
    another_field = _evidence_ref(
        evidence_id="ev-003",
        field_path="chapter_contract.functions[1]",
        excerpt=original.excerpt,
    )

    assert deduplicate_evidence_refs((original, same_binding, another_field)) == (original, another_field)


@pytest.mark.parametrize(
    ("ref_changes", "source_changes", "expected_code"),
    [
        ({}, {"source_content_hash": "b" * 64}, "evidence_hash_mismatch"),
        ({}, {"source_version": "v2"}, "evidence_version_mismatch"),
        ({}, {"located_excerpts": ()}, "evidence_locator_unresolved"),
        ({}, {"assertions_by_field_path": ()}, "evidence_assertion_mismatch"),
    ],
)
def test_integrity_validator_reports_source_drift(ref_changes, source_changes, expected_code):
    ref = _evidence_ref(**ref_changes)
    source = _resolved_source(**source_changes)

    issues = EvidenceIntegrityValidator(lambda source_id: source).validate(ref, ref.field_path)

    assert [issue.code for issue in issues] == [expected_code]
    assert all(issue.blocking for issue in issues)
    assert all(issue.field_path == ref.field_path for issue in issues)


def test_integrity_validator_binds_authoritative_excerpt_and_structured_value_to_candidate_value():
    ref = _evidence_ref()
    validator = EvidenceIntegrityValidator(lambda source_id: _resolved_source())

    assert validator.validate(ref, ref.field_path, expected_value="推进主线", require_source_kind=True) == ()

    excerpt_issues = validator.validate(
        _evidence_ref(excerpt="伪造摘录"),
        ref.field_path,
        expected_value="推进主线",
        require_source_kind=True,
    )
    ref_value_issues = validator.validate(
        _evidence_ref(asserted_value="改变人物关系"),
        ref.field_path,
        expected_value="推进主线",
        require_source_kind=True,
    )
    source_value_issues = EvidenceIntegrityValidator(
        lambda source_id: _resolved_source(
            asserted_values=(EvidenceAssertion(ref.field_path, "改变人物关系"),)
        )
    ).validate(ref, ref.field_path, expected_value="推进主线", require_source_kind=True)

    assert [issue.code for issue in excerpt_issues] == ["evidence_excerpt_mismatch"]
    assert [issue.code for issue in ref_value_issues] == ["evidence_asserted_value_mismatch"]
    assert [issue.code for issue in source_value_issues] == ["evidence_asserted_value_mismatch"]


def test_integrity_validator_requires_strict_authoritative_source_kind_for_admission():
    source = _resolved_source(source_kind=None)

    result = EvidenceIntegrityValidator(lambda source_id: source).validate(
        _evidence_ref(),
        "chapter_contract.functions[0]",
        expected_value="推进主线",
        require_source_kind=True,
    )

    assert [issue.code for issue in result] == ["evidence_source_kind_missing"]


def test_structured_asserted_value_comparison_preserves_scalar_type():
    ref = _evidence_ref(asserted_value=True)
    source = _resolved_source(
        asserted_values=(EvidenceAssertion("chapter_contract.functions[0]", True),)
    )

    result = EvidenceIntegrityValidator(lambda source_id: source).validate(
        ref,
        "chapter_contract.functions[0]",
        expected_value=1,
        require_source_kind=True,
    )

    assert [issue.code for issue in result] == ["evidence_asserted_value_mismatch"]


def test_integrity_validator_rejects_memory_evidence_as_field_evidence():
    from creative_os.memory.model import MemoryEvidence

    validator = EvidenceIntegrityValidator(lambda source_id: _resolved_source())

    issues = validator.validate(
        MemoryEvidence(source_type="review", source_id="run-12"),
        "chapter_contract.functions[0]",
    )

    assert [issue.code for issue in issues] == ["evidence_ref_required"]


def test_replay_evidence_ref_is_the_single_public_evidence_ref_type():
    legacy_ref = ReplayEvidenceRef("task", "production/chapter_001/tasks/scene.json", "goal: 推进主线")
    class_definitions = []
    for path in Path("creative_os").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        class_definitions.extend(path for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == "EvidenceRef")

    assert ReplayEvidenceRef is EvidenceRef
    assert legacy_ref.source_type == "task"
    assert legacy_ref.source_ref == "production/chapter_001/tasks/scene.json"
    assert len(class_definitions) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"located_excerpts": []},
        {"located_excerpts": ([EvidenceLocator(kind="json_pointer", value="/functions/0"), "文本"],)},
        {"assertions_by_field_path": []},
        {"assertions_by_field_path": (("chapter_contract.functions[0]", ["断言"]),)},
        {"asserted_values": []},
    ],
)
def test_resolved_evidence_source_rejects_mutable_nested_containers(changes):
    with pytest.raises(ValueError, match="tuple"):
        _resolved_source(**changes)


@pytest.mark.parametrize(
    "resolver",
    [
        lambda source_id: RuntimeError("source failed"),
        lambda source_id: (_ for _ in ()).throw(RuntimeError("source failed")),
    ],
)
def test_integrity_validator_converts_invalid_resolver_results_to_blocking_issues(resolver):
    issues = EvidenceIntegrityValidator(resolver).validate(_evidence_ref(), "chapter_contract.functions[0]")

    assert [issue.code for issue in issues] == ["evidence_source_unavailable"]
    assert issues[0].blocking


def test_integrity_validator_converts_source_property_errors_to_blocking_issues():
    class ExplodingSource:
        @property
        def source_id(self):
            raise RuntimeError("source failed")

    issues = EvidenceIntegrityValidator(lambda source_id: ExplodingSource()).validate(
        _evidence_ref(),
        "chapter_contract.functions[0]",
    )

    assert [issue.code for issue in issues] == ["evidence_source_unavailable"]
    assert issues[0].blocking
