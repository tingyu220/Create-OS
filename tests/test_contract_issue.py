from dataclasses import FrozenInstanceError

import pytest

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck


def test_contract_issue_requires_all_public_fields_and_is_frozen():
    check = EvidenceCheck(code="source_hash_matches", passed=True, detail="匹配当前来源")
    issue = ContractIssue(
        code="evidence_hash_mismatch",
        severity="error",
        blocking=True,
        field_path="chapter_contract.functions[0]",
        evidence_checks=(check,),
        repair_hint="重新绑定当前来源版本。",
    )

    assert issue.evidence_checks == (check,)
    with pytest.raises(FrozenInstanceError):
        issue.code = "changed"  # type: ignore[misc]


def test_contract_issue_rejects_missing_required_values():
    with pytest.raises(ValueError, match="code"):
        ContractIssue(
            code="",
            severity="error",
            blocking=True,
            field_path="chapter_contract.functions[0]",
            evidence_checks=(),
            repair_hint="修复。",
        )


@pytest.mark.parametrize("passed", (1, 0))
def test_evidence_check_rejects_integer_passed_values(passed: int):
    with pytest.raises((TypeError, ValueError), match="passed"):
        EvidenceCheck(code="source_hash_matches", passed=passed, detail="匹配当前来源")


@pytest.mark.parametrize(
    "overrides",
    (
        {"code": 1},
        {"detail": 1},
        {"code": " "},
        {"detail": " "},
    ),
)
def test_evidence_check_requires_exact_non_empty_text(overrides: dict[str, object]):
    values: dict[str, object] = {
        "code": "source_hash_matches",
        "passed": True,
        "detail": "匹配当前来源",
    }
    values.update(overrides)

    with pytest.raises((TypeError, ValueError)):
        EvidenceCheck(**values)
