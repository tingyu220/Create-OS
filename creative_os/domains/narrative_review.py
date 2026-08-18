from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.narrative_decision import NarrativeDecision, NarrativeValidationError
from creative_os.domains.narrative_progression import evaluate_progression


TIME_OPENERS = ("凌晨", "清晨", "早晨", "上午", "中午", "午后", "傍晚", "夜晚", "深夜")


@dataclass(frozen=True, slots=True)
class NarrativeIssue:
    code: str
    severity: str
    evidence: str


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
    if not chapter.protagonist_choice.actor or not chapter.protagonist_choice.action:
        issues.append(NarrativeIssue("missing_protagonist_agency", "high", "chapter_contract.protagonist_choice"))
    if not chapter.protagonist_choice.cost or not chapter.protagonist_choice.consequence:
        issues.append(NarrativeIssue("missing_agency_cost_or_consequence", "high", "chapter_contract.protagonist_choice"))
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
