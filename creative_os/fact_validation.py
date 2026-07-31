from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FactValidationResult:
    fact: str
    supported: bool
    evidence: list[str]


def validate_required_facts(required_facts: list[str], text: str) -> list[FactValidationResult]:
    from creative_os.llm_writer import FACT_KEYWORD_ALIASES

    results: list[FactValidationResult] = []
    for fact in required_facts:
        matched_keys = [key for key in FACT_KEYWORD_ALIASES if key in fact]
        evidence = [
            key
            for key in matched_keys
            if any(alias in text for alias in FACT_KEYWORD_ALIASES[key])
        ]
        required_count = len(matched_keys) if len(matched_keys) <= 2 else len(matched_keys) - 1
        supported = bool(matched_keys) and len(evidence) >= required_count
        results.append(FactValidationResult(fact=fact, supported=supported, evidence=evidence))
    return results
