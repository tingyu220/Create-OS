from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from creative_os.domains.contract_issue import ContractIssue, EvidenceCheck


_SEVERITIES = frozenset({"high", "warning", "low"})
_DISPOSITION_STATUSES = frozenset({"accepted", "resolved"})
_SYSTEM_ACTORS = frozenset({"system", "assistant", "ai", "model", "automation", "bot"})


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} is required")
    return value


def _require_sha256(value: object, name: str) -> str:
    text = _require_text(value, name)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{name} must be a lowercase sha256")
    return text


def _canonical_json_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _check_payload(check: EvidenceCheck) -> dict[str, object]:
    return {"code": check.code, "detail": check.detail, "passed": check.passed}


def _canonical_checks(value: object) -> tuple[EvidenceCheck, ...]:
    if not isinstance(value, tuple):
        raise TypeError("review issue evidence_checks must be a tuple")
    if not value or not all(isinstance(check, EvidenceCheck) for check in value):
        raise ValueError("review issue evidence_checks must contain EvidenceCheck values")
    for check in value:
        if type(check.code) is not str or not check.code.strip():
            raise ValueError("review issue evidence check code must be exact non-empty text")
        if type(check.detail) is not str or not check.detail.strip():
            raise ValueError("review issue evidence check detail must be exact non-empty text")
        if type(check.passed) is not bool:
            raise TypeError("review issue evidence check passed must be an exact bool")
    canonical = tuple(sorted(value, key=lambda check: (check.code, check.passed, check.detail)))
    if len(set(canonical)) != len(canonical):
        raise ValueError("review issue evidence_checks must not contain duplicates")
    return canonical


def _evidence_hash(checks: tuple[EvidenceCheck, ...]) -> str:
    return _canonical_json_hash([_check_payload(check) for check in checks])


def _issue_hash(
    *,
    code: str,
    severity: str,
    blocking: bool,
    requires_human_disposition: bool,
    field_path: str,
    evidence_checks: tuple[EvidenceCheck, ...],
) -> str:
    return _canonical_json_hash(
        {
            "blocking": blocking,
            "code": code,
            "evidence_checks": [_check_payload(check) for check in evidence_checks],
            "field_path": field_path,
            "requires_human_disposition": requires_human_disposition,
            "severity": severity,
        }
    )


@dataclass(frozen=True, slots=True)
class ReviewIssue:
    """Immutable reviewer finding with content-addressed evidence and semantics."""

    issue_id: str
    canonical_issue_hash: str
    code: str
    severity: str
    blocking: bool
    requires_human_disposition: bool
    field_path: str
    evidence_checks: tuple[EvidenceCheck, ...]
    evidence_hash: str
    repair_hint: str

    def __post_init__(self) -> None:
        _require_text(self.issue_id, "review issue_id")
        _require_text(self.code, "review issue code")
        _require_text(self.field_path, "review issue field_path")
        _require_text(self.repair_hint, "review issue repair_hint")
        if self.severity not in _SEVERITIES:
            raise ValueError("review issue severity must be high, warning or low")
        if not isinstance(self.blocking, bool):
            raise TypeError("review issue blocking must be a bool")
        if not isinstance(self.requires_human_disposition, bool):
            raise TypeError("review issue requires_human_disposition must be a bool")
        if self.severity == "high" and not self.blocking:
            raise ValueError("high review issues must be blocking")
        canonical_checks = _canonical_checks(self.evidence_checks)
        if self.evidence_checks != canonical_checks:
            raise ValueError("review issue evidence_checks must be in canonical order")
        _require_sha256(self.evidence_hash, "review issue evidence_hash")
        if self.evidence_hash != _evidence_hash(canonical_checks):
            raise ValueError("review issue evidence_hash mismatch")
        _require_sha256(self.canonical_issue_hash, "review issue canonical_issue_hash")
        if self.canonical_issue_hash != _issue_hash(
            code=self.code,
            severity=self.severity,
            blocking=self.blocking,
            requires_human_disposition=self.requires_human_disposition,
            field_path=self.field_path,
            evidence_checks=canonical_checks,
        ):
            raise ValueError("review issue canonical_issue_hash mismatch")

    @classmethod
    def build(
        cls,
        *,
        issue_id: str,
        code: str,
        severity: str,
        blocking: bool,
        requires_human_disposition: bool,
        field_path: str,
        evidence_checks: tuple[EvidenceCheck, ...],
        repair_hint: str,
    ) -> ReviewIssue:
        canonical_checks = _canonical_checks(evidence_checks)
        return cls(
            issue_id=issue_id,
            canonical_issue_hash=_issue_hash(
                code=code,
                severity=severity,
                blocking=blocking,
                requires_human_disposition=requires_human_disposition,
                field_path=field_path,
                evidence_checks=canonical_checks,
            ),
            code=code,
            severity=severity,
            blocking=blocking,
            requires_human_disposition=requires_human_disposition,
            field_path=field_path,
            evidence_checks=canonical_checks,
            evidence_hash=_evidence_hash(canonical_checks),
            repair_hint=repair_hint,
        )


def _canonical_asset_versions(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, tuple):
        raise TypeError("semantic_asset_versions must be a tuple")
    if not value:
        raise ValueError("semantic_asset_versions are required")
    normalized: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("semantic_asset_versions entries must be name/version pairs")
        name, version = item
        normalized.append(
            (_require_text(name, "semantic asset name"), _require_text(version, "semantic asset version"))
        )
    canonical = tuple(sorted(normalized))
    if len({name for name, _ in canonical}) != len(canonical):
        raise ValueError("semantic asset names must be unique")
    return canonical


def _issue_payload(issue: ReviewIssue) -> dict[str, object]:
    return {
        "blocking": issue.blocking,
        "canonical_issue_hash": issue.canonical_issue_hash,
        "code": issue.code,
        "evidence_checks": [_check_payload(check) for check in issue.evidence_checks],
        "evidence_hash": issue.evidence_hash,
        "field_path": issue.field_path,
        "issue_id": issue.issue_id,
        "repair_hint": issue.repair_hint,
        "requires_human_disposition": issue.requires_human_disposition,
        "severity": issue.severity,
    }


def _canonical_issues(value: object) -> tuple[ReviewIssue, ...]:
    if not isinstance(value, tuple):
        raise TypeError("reviewer result issues must be a tuple")
    if not all(isinstance(issue, ReviewIssue) for issue in value):
        raise ValueError("reviewer result issues must contain ReviewIssue values")
    canonical = tuple(
        sorted(
            value,
            key=lambda issue: (issue.field_path, issue.code, issue.canonical_issue_hash, issue.issue_id),
        )
    )
    if len({issue.issue_id for issue in canonical}) != len(canonical):
        raise ValueError("reviewer result issue ids must be unique")
    if len({issue.canonical_issue_hash for issue in canonical}) != len(canonical):
        raise ValueError("reviewer result canonical issues must be unique")
    return canonical


def _result_hash(
    *,
    result_id: str,
    contract_id: str,
    contract_version: int,
    contract_content_hash: str,
    baseline_fingerprint: str,
    ruleset_version: str,
    semantic_asset_versions: tuple[tuple[str, str], ...],
    issues: tuple[ReviewIssue, ...],
) -> str:
    return _canonical_json_hash(
        {
            "baseline_fingerprint": baseline_fingerprint,
            "contract_content_hash": contract_content_hash,
            "contract_id": contract_id,
            "contract_version": contract_version,
            "issues": [_issue_payload(issue) for issue in issues],
            "result_id": result_id,
            "ruleset_version": ruleset_version,
            "semantic_asset_versions": [list(item) for item in semantic_asset_versions],
        }
    )


@dataclass(frozen=True, slots=True)
class PrewriteReviewerResult:
    """Versioned reviewer output bound to one exact candidate and review asset set."""

    result_id: str
    contract_id: str
    contract_version: int
    contract_content_hash: str
    baseline_fingerprint: str
    ruleset_version: str
    semantic_asset_versions: tuple[tuple[str, str], ...]
    issues: tuple[ReviewIssue, ...]
    result_hash: str

    def __post_init__(self) -> None:
        _require_text(self.result_id, "reviewer result_id")
        _require_text(self.contract_id, "reviewer contract_id")
        if type(self.contract_version) is not int or self.contract_version < 1:
            raise ValueError("reviewer contract_version must be a positive integer")
        _require_sha256(self.contract_content_hash, "reviewer contract_content_hash")
        _require_sha256(self.baseline_fingerprint, "reviewer baseline_fingerprint")
        _require_text(self.ruleset_version, "reviewer ruleset_version")
        canonical_assets = _canonical_asset_versions(self.semantic_asset_versions)
        if self.semantic_asset_versions != canonical_assets:
            raise ValueError("semantic_asset_versions must be in canonical order")
        canonical_issues = _canonical_issues(self.issues)
        if self.issues != canonical_issues:
            raise ValueError("reviewer result issues must be in canonical order")
        for issue in canonical_issues:
            _validate_issue_integrity(issue)
        _require_sha256(self.result_hash, "reviewer result_hash")
        if self.result_hash != _result_hash(
            result_id=self.result_id,
            contract_id=self.contract_id,
            contract_version=self.contract_version,
            contract_content_hash=self.contract_content_hash,
            baseline_fingerprint=self.baseline_fingerprint,
            ruleset_version=self.ruleset_version,
            semantic_asset_versions=canonical_assets,
            issues=canonical_issues,
        ):
            raise ValueError("reviewer result_hash mismatch")

    @classmethod
    def build(
        cls,
        *,
        result_id: str,
        contract_id: str,
        contract_version: int,
        contract_content_hash: str,
        baseline_fingerprint: str,
        ruleset_version: str,
        semantic_asset_versions: tuple[tuple[str, str], ...],
        issues: tuple[ReviewIssue, ...],
    ) -> PrewriteReviewerResult:
        canonical_assets = _canonical_asset_versions(semantic_asset_versions)
        canonical_issues = _canonical_issues(issues)
        return cls(
            result_id=result_id,
            contract_id=contract_id,
            contract_version=contract_version,
            contract_content_hash=contract_content_hash,
            baseline_fingerprint=baseline_fingerprint,
            ruleset_version=ruleset_version,
            semantic_asset_versions=canonical_assets,
            issues=canonical_issues,
            result_hash=_result_hash(
                result_id=result_id,
                contract_id=contract_id,
                contract_version=contract_version,
                contract_content_hash=contract_content_hash,
                baseline_fingerprint=baseline_fingerprint,
                ruleset_version=ruleset_version,
                semantic_asset_versions=canonical_assets,
                issues=canonical_issues,
            ),
        )


@dataclass(frozen=True, slots=True)
class ReviewIssueDisposition:
    """A human decision bound to one exact issue in one exact reviewer result."""

    issue_id: str
    canonical_issue_hash: str
    issue_code: str
    field_path: str
    evidence_hash: str
    status: str
    reason: str
    actor: str
    decided_at: str
    reviewer_result_id: str
    reviewer_result_hash: str

    def __post_init__(self) -> None:
        _validate_disposition(self, raise_on_error=True)


@dataclass(frozen=True, slots=True)
class ReviewerGateResult:
    issues: tuple[ContractIssue, ...]

    @property
    def is_ready(self) -> bool:
        return not any(issue.blocking for issue in self.issues)

    @property
    def issue_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


def validate_reviewer_gate(
    reviewer_result: object,
    dispositions: tuple[ReviewIssueDisposition, ...] = (),
    *,
    contract_id: str,
    contract_version: int,
    contract_content_hash: str,
    baseline_fingerprint: str,
    ruleset_version: str,
    semantic_asset_versions: tuple[tuple[str, str], ...],
) -> ReviewerGateResult:
    """Validate current bindings and exact human dispositions without side effects."""

    if reviewer_result is None:
        return ReviewerGateResult((_gate_issue("missing_prewrite_review"),))
    if not isinstance(reviewer_result, PrewriteReviewerResult) or not _result_is_current(
        reviewer_result,
        contract_id=contract_id,
        contract_version=contract_version,
        contract_content_hash=contract_content_hash,
        baseline_fingerprint=baseline_fingerprint,
        ruleset_version=ruleset_version,
        semantic_asset_versions=semantic_asset_versions,
    ):
        return ReviewerGateResult((_gate_issue("stale_prewrite_review"),))
    if not isinstance(dispositions, tuple) or not all(
        isinstance(disposition, ReviewIssueDisposition) for disposition in dispositions
    ):
        return ReviewerGateResult((_gate_issue("unresolved_review_warning"),))

    required = tuple(
        issue
        for issue in reviewer_result.issues
        if issue.severity != "high" and (issue.blocking or issue.requires_human_disposition)
    )
    high_issues = tuple(issue for issue in reviewer_result.issues if issue.severity == "high")
    matched_indexes: set[int] = set()
    unresolved = bool(high_issues)

    for issue in required:
        matches = tuple(
            index
            for index, disposition in enumerate(dispositions)
            if _disposition_matches(disposition, reviewer_result, issue)
        )
        if len(matches) != 1:
            unresolved = True
        else:
            matched_indexes.add(matches[0])
    if len(matched_indexes) != len(dispositions):
        unresolved = True
    return ReviewerGateResult((_gate_issue("unresolved_review_warning"),) if unresolved else ())


def _validate_issue_integrity(issue: ReviewIssue) -> None:
    canonical_checks = _canonical_checks(issue.evidence_checks)
    if issue.evidence_checks != canonical_checks:
        raise ValueError("review issue evidence_checks must be in canonical order")
    if issue.evidence_hash != _evidence_hash(canonical_checks):
        raise ValueError("review issue evidence_hash mismatch")
    if issue.canonical_issue_hash != _issue_hash(
        code=issue.code,
        severity=issue.severity,
        blocking=issue.blocking,
        requires_human_disposition=issue.requires_human_disposition,
        field_path=issue.field_path,
        evidence_checks=canonical_checks,
    ):
        raise ValueError("review issue canonical_issue_hash mismatch")


def _result_is_current(result: PrewriteReviewerResult, **expected: object) -> bool:
    try:
        _validate_expected_bindings(expected)
        canonical_assets = _canonical_asset_versions(expected["semantic_asset_versions"])
        result_assets = _canonical_asset_versions(result.semantic_asset_versions)
        canonical_issues = _canonical_issues(result.issues)
        for issue in canonical_issues:
            _validate_issue_integrity(issue)
        expected_hash = _result_hash(
            result_id=result.result_id,
            contract_id=result.contract_id,
            contract_version=result.contract_version,
            contract_content_hash=result.contract_content_hash,
            baseline_fingerprint=result.baseline_fingerprint,
            ruleset_version=result.ruleset_version,
            semantic_asset_versions=result.semantic_asset_versions,
            issues=canonical_issues,
        )
        return (
            result.issues == canonical_issues
            and result.semantic_asset_versions == result_assets
            and result.result_hash == expected_hash
            and result.contract_id == expected["contract_id"]
            and result.contract_version == expected["contract_version"]
            and result.contract_content_hash == expected["contract_content_hash"]
            and result.baseline_fingerprint == expected["baseline_fingerprint"]
            and result.ruleset_version == expected["ruleset_version"]
            and result.semantic_asset_versions == canonical_assets
        )
    except Exception:
        return False


def _validate_expected_bindings(expected: dict[str, object]) -> None:
    for name in ("contract_id", "ruleset_version"):
        value = expected[name]
        if type(value) is not str or not value.strip():
            raise ValueError(f"expected {name} must be non-empty exact text")
    if type(expected["contract_version"]) is not int or expected["contract_version"] < 1:
        raise ValueError("expected contract_version must be an exact positive integer")
    for name in ("contract_content_hash", "baseline_fingerprint"):
        value = expected[name]
        if type(value) is not str:
            raise TypeError(f"expected {name} must be exact text")
        _require_sha256(value, f"expected {name}")
    assets = expected["semantic_asset_versions"]
    if type(assets) is not tuple:
        raise TypeError("expected semantic_asset_versions must be an exact tuple")
    for item in assets:
        if type(item) is not tuple or len(item) != 2:
            raise ValueError("expected semantic_asset_versions entries must be exact pairs")
        if any(type(value) is not str or not value.strip() for value in item):
            raise ValueError("expected semantic asset names and versions must be exact text")


def _validate_disposition(disposition: ReviewIssueDisposition, *, raise_on_error: bool) -> bool:
    try:
        _require_text(disposition.issue_id, "disposition issue_id")
        _require_sha256(disposition.canonical_issue_hash, "disposition canonical_issue_hash")
        _require_text(disposition.issue_code, "disposition issue_code")
        _require_text(disposition.field_path, "disposition field_path")
        _require_sha256(disposition.evidence_hash, "disposition evidence_hash")
        if disposition.status not in _DISPOSITION_STATUSES:
            raise ValueError("disposition status must be accepted or resolved")
        _require_text(disposition.reason, "disposition reason")
        actor = _require_text(disposition.actor, "disposition actor")
        if actor.strip().casefold() in _SYSTEM_ACTORS:
            raise ValueError("disposition actor must identify a human")
        timestamp = _require_text(disposition.decided_at, "disposition decided_at")
        parsed = datetime.fromisoformat(timestamp)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("disposition decided_at must include a timezone")
        _require_text(disposition.reviewer_result_id, "disposition reviewer_result_id")
        _require_sha256(disposition.reviewer_result_hash, "disposition reviewer_result_hash")
    except (TypeError, ValueError):
        if raise_on_error:
            raise
        return False
    return True


def _disposition_matches(
    disposition: ReviewIssueDisposition,
    result: PrewriteReviewerResult,
    issue: ReviewIssue,
) -> bool:
    return _validate_disposition(disposition, raise_on_error=False) and (
        disposition.issue_id == issue.issue_id
        and disposition.canonical_issue_hash == issue.canonical_issue_hash
        and disposition.issue_code == issue.code
        and disposition.field_path == issue.field_path
        and disposition.evidence_hash == issue.evidence_hash
        and disposition.reviewer_result_id == result.result_id
        and disposition.reviewer_result_hash == result.result_hash
    )


def _gate_issue(code: str) -> ContractIssue:
    repair_hint = {
        "missing_prewrite_review": "生成绑定当前合同、baseline 与规则资产的预写审阅结果。",
        "stale_prewrite_review": "对当前合同、baseline 与规则资产重新执行预写审阅。",
        "unresolved_review_warning": "由人类逐项裁决当前审阅结果中的阻断问题。",
    }[code]
    return ContractIssue(
        code=code,
        severity="high",
        blocking=True,
        field_path="reviewer_result",
        evidence_checks=(EvidenceCheck(code=code, passed=False, detail=repair_hint),),
        repair_hint=repair_hint,
    )
