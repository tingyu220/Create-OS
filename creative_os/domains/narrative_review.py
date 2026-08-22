from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from creative_os.domains.narrative_decision import ChoiceStatus, NarrativeDecision, NarrativeValidationError
from creative_os.domains.narrative_evidence import EvidenceRef
from creative_os.domains.narrative_progression import evaluate_progression
from creative_os.domains.narrative_replay_model import (
    ReplayNarrativeIssue,
    ReplayedChapterContract,
    UNKNOWN,
)
from creative_os.domains.contract_fulfillment import ContractFulfillmentEvidenceRecord
from creative_os.domains.contract_fulfillment_store import ContractFulfillmentStore


TIME_OPENERS = ("凌晨", "清晨", "早晨", "上午", "中午", "午后", "傍晚", "夜晚", "深夜")


def append_fulfillment_records(store: object, records: Iterable[ContractFulfillmentEvidenceRecord]) -> tuple[ContractFulfillmentEvidenceRecord, ...]:
    """Reviewer output is append-only; fulfillment evaluation remains a separate pure step."""
    if type(store) is not ContractFulfillmentStore:
        raise TypeError("store must be ContractFulfillmentStore")
    append = store.append
    result = []
    for record in records:
        if not isinstance(record, ContractFulfillmentEvidenceRecord):
            raise TypeError("records must contain ContractFulfillmentEvidenceRecord")
        result.append(append(record))
    return tuple(result)


@dataclass(frozen=True, slots=True)
class NarrativeIssue:
    code: str
    severity: str
    evidence: str


def review_replayed_contract(
    contract: ReplayedChapterContract,
    recent: tuple[ReplayedChapterContract, ...] = (),
) -> tuple[ReplayNarrativeIssue, ...]:
    contract.validate()
    issues: list[ReplayNarrativeIssue] = []

    issues.extend(_review_replayed_choice(contract))

    if contract.reader_before == UNKNOWN or contract.reader_after == UNKNOWN:
        issues.append(_replay_issue(
            "unknown_reader_change",
            "读者认知前后变化缺少明确证据。",
            contract,
            "人工标注本章揭示、隐藏或误导的信息变化。",
        ))

    current_functions = {item for item in contract.functions if item != UNKNOWN}
    for previous in reversed(recent):
        overlap = current_functions & {item for item in previous.functions if item != UNKNOWN}
        if overlap:
            issues.append(ReplayNarrativeIssue(
                code="repeated_chapter_function",
                severity="warning",
                message=f"与近期章节重复功能：{'、'.join(sorted(overlap))}",
                evidence=_unique_replay_evidence((*contract.evidence, *previous.evidence)),
                repair_hint="人工判断该重复是否承担升级、转折或兑现功能；否则调整章节职责。",
            ))
            break

    if contract.ending_shift == UNKNOWN:
        issues.append(_replay_issue(
            "unknown_ending_shift",
            "章节结尾的新失衡缺少明确证据。",
            contract,
            "人工确认结尾改变了哪项风险、关系、信息或行动条件。",
        ))
    return tuple(issues)


def review_narrative(
    contract: NarrativeDecision,
    recent_contracts: list[NarrativeDecision],
    text: str,
) -> list[NarrativeIssue]:
    issues: list[NarrativeIssue] = []
    try:
        contract.validate()
    except NarrativeValidationError as error:
        issues.append(NarrativeIssue("incomplete_chapter_contract", "high", str(error)))

    chapter = contract.chapter_contract
    issues.extend(_review_choice(chapter.protagonist_choice))
    if not chapter.reader_change.before or not chapter.reader_change.after:
        issues.append(NarrativeIssue("missing_reader_change", "high", "chapter_contract.reader_change"))
    if not chapter.foreshadow_actions:
        issues.append(NarrativeIssue("missing_foreshadow_action", "medium", "chapter_contract.foreshadow_actions"))
    if not chapter.ending_shift:
        issues.append(NarrativeIssue("missing_ending_shift", "medium", "chapter_contract.ending_shift"))

    current_functions = set(chapter.functions)
    for recent in recent_contracts[-2:]:
        overlap = current_functions & set(recent.chapter_contract.functions)
        if overlap:
            issues.append(
                NarrativeIssue("duplicate_recent_function", "medium", f"functions: {', '.join(sorted(overlap))}")
            )
            break

    opener = _opening(text)
    if recent_contracts and opener and any(opener.startswith(word) for word in TIME_OPENERS):
        issues.append(NarrativeIssue("repeated_time_opening", "low", opener))

    for forbidden in chapter.forbidden:
        if forbidden and forbidden in text:
            issues.append(NarrativeIssue("forbidden_information_revealed", "high", forbidden))
    for progression_issue in evaluate_progression(contract, recent_contracts).issues:
        issues.append(NarrativeIssue(
            progression_issue.code, progression_issue.severity, progression_issue.evidence,
        ))
    return issues


def _opening(text: str) -> str:
    for line in text.splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value[:120]
    return ""


def _replay_issue(
    code: str,
    message: str,
    contract: ReplayedChapterContract,
    repair_hint: str,
) -> ReplayNarrativeIssue:
    return ReplayNarrativeIssue(
        code=code,
        severity="warning",
        message=message,
        evidence=contract.evidence,
        repair_hint=repair_hint,
    )


def _review_replayed_choice(contract: ReplayedChapterContract) -> tuple[ReplayNarrativeIssue, ...]:
    choice = contract.protagonist_choice
    if choice is None or choice.status == ChoiceStatus.UNKNOWN:
        return (
            _choice_replay_issue(
                "missing_protagonist_choice",
                "没有结构化证据证明主角在本章作出主动选择。",
                "人工核对任务与正文；确认后补录人物选择状态证据。",
            ),
        )

    issues: list[ReplayNarrativeIssue] = []
    if choice.status == ChoiceStatus.PARTIAL:
        missing = "、".join(choice.missing_fields)
        issues.append(_choice_replay_issue(
            "partial_protagonist_choice",
            f"人物选择仅部分可确认，缺失字段：{missing}。",
            "逐项核对并补录人物选择缺失字段的精确证据。",
        ))

    missing_fields = set(choice.missing_fields)
    if "alternatives" in missing_fields or not choice.alternatives or all(
        not value.strip() or value == UNKNOWN for value in choice.alternatives
    ):
        issues.append(_choice_replay_issue(
            "missing_choice_alternatives",
            "人物选择缺少可确认的替代方案。",
            "人工确认主角放弃了哪些替代方案并补录精确证据。",
        ))
    if "cost" in missing_fields or not choice.cost or not choice.cost.strip() or choice.cost == UNKNOWN:
        issues.append(_choice_replay_issue(
            "missing_choice_cost",
            "人物选择缺少可确认的代价。",
            "人工确认选择造成的即时或延迟代价并补录精确证据。",
        ))
    if (
        "consequence" in missing_fields
        or not choice.consequence
        or not choice.consequence.strip()
        or choice.consequence == UNKNOWN
    ):
        issues.append(_choice_replay_issue(
            "missing_choice_consequence",
            "人物选择缺少可确认的后果。",
            "人工确认选择改变的后续行动条件并补录精确证据。",
        ))
    return tuple(issues)


def _choice_replay_issue(code: str, message: str, repair_hint: str) -> ReplayNarrativeIssue:
    """Choice gaps cannot inherit unscoped whole-chapter evidence."""

    return ReplayNarrativeIssue(
        code=code,
        severity="warning",
        message=message,
        evidence=(),
        repair_hint=repair_hint,
    )


def _review_choice(choice: object) -> tuple[NarrativeIssue, ...]:
    status = getattr(choice, "status", None)
    if status == ChoiceStatus.UNKNOWN:
        return (
            NarrativeIssue(
                "missing_protagonist_choice",
                "high",
                "chapter_contract.protagonist_choice.status",
            ),
        )

    issues: list[NarrativeIssue] = []
    missing_fields = set(getattr(choice, "missing_fields", ()))
    if status == ChoiceStatus.PARTIAL:
        issues.extend(
            NarrativeIssue(
                "partial_protagonist_choice",
                "high",
                f"chapter_contract.protagonist_choice.{name}",
            )
            for name in getattr(choice, "missing_fields", ())
        )
    alternatives = getattr(choice, "alternatives", ())
    if "alternatives" in missing_fields or not alternatives:
        issues.append(NarrativeIssue(
            "missing_choice_alternatives",
            "high",
            "chapter_contract.protagonist_choice.alternatives",
        ))
    else:
        for index, alternative in enumerate(alternatives):
            if not isinstance(alternative, str) or not alternative.strip() or alternative == UNKNOWN:
                issues.append(NarrativeIssue(
                    "missing_choice_alternatives",
                    "high",
                    f"chapter_contract.protagonist_choice.alternatives[{index}]",
                ))
    for name, code in (
        ("cost", "missing_choice_cost"),
        ("consequence", "missing_choice_consequence"),
    ):
        value = getattr(choice, name, None)
        missing = name in missing_fields or not value
        if isinstance(value, str):
            missing = missing or not value.strip() or value == UNKNOWN
        if missing:
            issues.append(NarrativeIssue(code, "high", f"chapter_contract.protagonist_choice.{name}"))
    return tuple(issues)


def _unique_replay_evidence(values: Iterable[EvidenceRef]) -> tuple[EvidenceRef, ...]:
    result: list[EvidenceRef] = []
    seen: set[tuple[str, str, str]] = set()
    for value in values:
        marker = (value.source_type, value.source_ref, value.excerpt)
        if marker not in seen:
            seen.add(marker)
            result.append(value)
    return tuple(result)
