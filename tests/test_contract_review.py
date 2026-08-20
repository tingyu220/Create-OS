from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from creative_os.domains.contract_issue import EvidenceCheck
from creative_os.domains.contract_review import (
    PrewriteReviewerResult,
    ReviewIssue,
    ReviewIssueDisposition,
    validate_reviewer_gate,
)


def _sha(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _checks(detail: str = "未找到字段证据") -> tuple[EvidenceCheck, ...]:
    return (
        EvidenceCheck("source_scanned", True, "已扫描任务来源"),
        EvidenceCheck("field_found", False, detail),
    )


def _issue(
    *,
    issue_id: str = "issue-cost",
    code: str = "missing_choice_cost",
    severity: str = "warning",
    blocking: bool = True,
    requires_human_disposition: bool = False,
    field_path: str = "chapter_contract.protagonist_choice.cost",
    evidence_checks: tuple[EvidenceCheck, ...] | None = None,
    repair_hint: str = "补充选择代价",
) -> ReviewIssue:
    return ReviewIssue.build(
        issue_id=issue_id,
        code=code,
        severity=severity,
        blocking=blocking,
        requires_human_disposition=requires_human_disposition,
        field_path=field_path,
        evidence_checks=evidence_checks or _checks(),
        repair_hint=repair_hint,
    )


def _result(
    issues: tuple[ReviewIssue, ...] = (),
    **overrides: object,
) -> PrewriteReviewerResult:
    values: dict[str, object] = {
        "result_id": "review-001",
        "contract_id": "narrative-chapter-007",
        "contract_version": 3,
        "contract_content_hash": "a" * 64,
        "baseline_fingerprint": "b" * 64,
        "ruleset_version": "prewrite-review-v1",
        "semantic_asset_versions": (
            ("entity_slots", "v1"),
            ("function_semantics", "v1"),
        ),
        "issues": issues,
    }
    values.update(overrides)
    return PrewriteReviewerResult.build(**values)


def _gate(result: object, dispositions: tuple[ReviewIssueDisposition, ...] = (), **overrides: object):
    values: dict[str, object] = {
        "contract_id": "narrative-chapter-007",
        "contract_version": 3,
        "contract_content_hash": "a" * 64,
        "baseline_fingerprint": "b" * 64,
        "ruleset_version": "prewrite-review-v1",
        "semantic_asset_versions": (
            ("entity_slots", "v1"),
            ("function_semantics", "v1"),
        ),
    }
    values.update(overrides)
    return validate_reviewer_gate(result, dispositions, **values)


def _disposition(
    result: PrewriteReviewerResult,
    issue: ReviewIssue,
    **overrides: object,
) -> ReviewIssueDisposition:
    values: dict[str, object] = {
        "issue_id": issue.issue_id,
        "canonical_issue_hash": issue.canonical_issue_hash,
        "issue_code": issue.code,
        "field_path": issue.field_path,
        "evidence_hash": issue.evidence_hash,
        "status": "accepted",
        "reason": "该缺口已由主编确认可接受",
        "actor": "editor-tingyu",
        "decided_at": "2026-08-20T10:30:00+08:00",
        "reviewer_result_id": result.result_id,
        "reviewer_result_hash": result.result_hash,
    }
    values.update(overrides)
    return ReviewIssueDisposition(**values)


class _TextSubclass(str):
    pass


def test_review_issue_hashes_cover_exact_canonical_fields_and_checks_are_order_independent():
    checks = _checks()
    issue = _issue(evidence_checks=checks)
    reordered = _issue(evidence_checks=tuple(reversed(checks)))
    canonical_checks = [
        {"code": "field_found", "detail": "未找到字段证据", "passed": False},
        {"code": "source_scanned", "detail": "已扫描任务来源", "passed": True},
    ]

    assert issue.evidence_checks == tuple(reversed(checks))
    assert issue.evidence_hash == _sha(canonical_checks)
    assert issue.canonical_issue_hash == _sha(
        {
            "blocking": True,
            "code": "missing_choice_cost",
            "evidence_checks": canonical_checks,
            "field_path": "chapter_contract.protagonist_choice.cost",
            "requires_human_disposition": False,
            "severity": "warning",
        }
    )
    assert reordered == issue

    mutations = (
        _issue(code="other_code"),
        _issue(severity="low", blocking=False),
        _issue(blocking=False),
        _issue(requires_human_disposition=True),
        _issue(field_path="chapter_contract.protagonist_choice.consequence"),
        _issue(evidence_checks=_checks("另一个检查结果")),
    )
    assert all(candidate.canonical_issue_hash != issue.canonical_issue_hash for candidate in mutations)


def test_review_issue_revalidates_tampered_evidence_check_scalar_types():
    check = EvidenceCheck("field_found", False, "未找到字段证据")
    object.__setattr__(check, "passed", 1)

    with pytest.raises((TypeError, ValueError), match="passed"):
        _issue(evidence_checks=(check,))


def test_result_hash_covers_every_binding_and_full_canonical_issue_in_stable_order():
    cost = _issue()
    consequence = _issue(
        issue_id="issue-consequence",
        code="missing_choice_consequence",
        field_path="chapter_contract.protagonist_choice.consequence",
        repair_hint="补充选择后果",
    )
    result = _result((consequence, cost))
    reordered = _result(
        (cost, consequence),
        semantic_asset_versions=(("function_semantics", "v1"), ("entity_slots", "v1")),
    )

    assert result == reordered
    assert result.issues == (consequence, cost)
    assert result.semantic_asset_versions == (("entity_slots", "v1"), ("function_semantics", "v1"))

    mutations = (
        _result((cost, consequence), result_id="review-002"),
        _result((cost, consequence), contract_id="narrative-chapter-008"),
        _result((cost, consequence), contract_version=4),
        _result((cost, consequence), contract_content_hash="c" * 64),
        _result((cost, consequence), baseline_fingerprint="d" * 64),
        _result((cost, consequence), ruleset_version="prewrite-review-v2"),
        _result((cost, consequence), semantic_asset_versions=(("function_semantics", "v2"),)),
        _result((_issue(repair_hint="改为人工核对代价"), consequence)),
    )
    assert all(candidate.result_hash != result.result_hash for candidate in mutations)


def test_reviewer_result_rejects_missing_semantic_asset_bindings():
    with pytest.raises(ValueError, match="semantic_asset_versions"):
        _result(semantic_asset_versions=())


def test_gate_blocks_missing_result_and_every_stale_binding():
    assert _gate(None).issue_codes == ("missing_prewrite_review",)
    result = _result()

    stale_cases = (
        {"contract_id": "narrative-chapter-008"},
        {"contract_version": 4},
        {"contract_content_hash": "c" * 64},
        {"baseline_fingerprint": "d" * 64},
        {"ruleset_version": "prewrite-review-v2"},
        {"semantic_asset_versions": (("function_semantics", "v2"),)},
    )
    for bindings in stale_cases:
        gate = _gate(result, **bindings)
        assert not gate.is_ready
        assert gate.issue_codes == ("stale_prewrite_review",)

    object.__setattr__(result, "result_hash", "f" * 64)
    assert _gate(result).issue_codes == ("stale_prewrite_review",)


@pytest.mark.parametrize(
    "overrides",
    (
        {"contract_version": True},
        {"contract_version": "1"},
        {"contract_version": 0},
        {"contract_id": _TextSubclass("narrative-chapter-007")},
        {"contract_content_hash": _TextSubclass("a" * 64)},
        {"baseline_fingerprint": _TextSubclass("b" * 64)},
        {"ruleset_version": _TextSubclass("prewrite-review-v1")},
        {
            "semantic_asset_versions": (
                (_TextSubclass("entity_slots"), "v1"),
                ("function_semantics", "v1"),
            )
        },
    ),
)
def test_gate_rejects_non_exact_expected_binding_types(overrides: dict[str, object]):
    result = _result(contract_version=1)
    expected = {"contract_version": 1, **overrides}

    gate = _gate(result, **expected)

    assert not gate.is_ready
    assert gate.issue_codes == ("stale_prewrite_review",)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("semantic_asset_versions", (("function_semantics", "v1"), ("function_semantics", "v2"))),
        ("issues", ("not-an-issue",)),
    ),
)
def test_gate_fails_closed_for_malformed_or_tampered_result_payload(field: str, value: object):
    result = _result()
    object.__setattr__(result, field, value)

    gate = _gate(result)

    assert not gate.is_ready
    assert gate.issue_codes == ("stale_prewrite_review",)


def test_high_issue_always_blocks_even_with_exact_human_disposition():
    issue = _issue(severity="high", blocking=True)
    result = _result((issue,))

    gate = _gate(result, (_disposition(result, issue, status="resolved"),))

    assert not gate.is_ready
    assert gate.issue_codes == ("unresolved_review_warning",)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("issue_id", "other-issue"),
        ("canonical_issue_hash", "c" * 64),
        ("issue_code", "missing_choice_consequence"),
        ("field_path", "chapter_contract.protagonist_choice.consequence"),
        ("evidence_hash", "d" * 64),
        ("reviewer_result_id", "review-002"),
        ("reviewer_result_hash", "e" * 64),
    ),
)
def test_warning_disposition_must_match_every_issue_and_result_binding(field: str, value: str):
    issue = _issue()
    result = _result((issue,))

    gate = _gate(result, (_disposition(result, issue, **{field: value}),))

    assert not gate.is_ready
    assert gate.issue_codes == ("unresolved_review_warning",)


@pytest.mark.parametrize(
    "override",
    (
        {"status": "rejected"},
        {"reason": " "},
        {"actor": "system"},
        {"decided_at": "2026-08-20T10:30:00"},
    ),
)
def test_disposition_requires_human_accepted_or_resolved_reason_actor_and_zoned_time(override):
    issue = _issue()
    result = _result((issue,))

    with pytest.raises(ValueError):
        _disposition(result, issue, **override)


def test_requires_human_low_issue_needs_exact_disposition_but_clean_result_needs_none():
    issue = _issue(severity="low", blocking=False, requires_human_disposition=True)
    result = _result((issue,))

    assert not _gate(result).is_ready
    assert _gate(result, (_disposition(result, issue, status="resolved"),)).is_ready
    assert _gate(_result()).is_ready


def test_same_code_with_different_path_or_evidence_cannot_share_disposition():
    cost = _issue()
    consequence = _issue(
        issue_id="issue-consequence",
        field_path="chapter_contract.protagonist_choice.consequence",
    )
    other_evidence = _issue(
        issue_id="issue-cost-second-source",
        evidence_checks=_checks("第二来源也未找到字段"),
    )
    result = _result((cost, consequence, other_evidence))

    gate = _gate(result, (_disposition(result, cost),))

    assert not gate.is_ready
    assert gate.issue_codes == ("unresolved_review_warning",)


def test_extra_duplicate_or_foreign_dispositions_fail_closed():
    issue = _issue()
    result = _result((issue,))
    exact = _disposition(result, issue)
    clean = _result()

    assert not _gate(result, (exact, exact)).is_ready
    assert not _gate(clean, (exact,)).is_ready

    foreign_issue = _issue(issue_id="foreign")
    foreign_result = _result((foreign_issue,), result_id="foreign-review")
    foreign = _disposition(foreign_result, foreign_issue)
    assert not _gate(result, (foreign,)).is_ready
