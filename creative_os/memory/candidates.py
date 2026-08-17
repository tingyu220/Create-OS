from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope


@dataclass(frozen=True, slots=True)
class CandidateExtractionInput:
    task_id: str
    project_id: str
    domain: str
    issues: list[str]
    attempts: int
    human_feedback: str
    source_ids: list[str]


def extract_candidates(payload: CandidateExtractionInput) -> list[MemoryItem]:
    normalized_issues = [_normalize(issue) for issue in payload.issues if issue.strip()]
    counts = Counter(normalized_issues)
    repeated = sorted(issue for issue, count in counts.items() if count >= 2)
    feedback = payload.human_feedback.strip()
    if not repeated and not feedback:
        return []

    contents = [feedback] if feedback else [f"避免重复出现质量问题：{issue}" for issue in repeated]
    issue_note = ", ".join(repeated or sorted(counts))
    evidence = tuple(
        MemoryEvidence(source_type="review", source_id=source_id, note=issue_note)
        for source_id in dict.fromkeys(payload.source_ids)
    )
    if not evidence:
        evidence = (MemoryEvidence(source_type="task", source_id=payload.task_id, note=issue_note),)

    candidates: list[MemoryItem] = []
    seen_ids: set[str] = set()
    for content in contents:
        item_id = _candidate_id(payload.domain, content)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        candidates.append(
            MemoryItem.new_candidate(
                id=item_id,
                kind=MemoryKind.EXPERIENCE,
                scope=MemoryScope.DOMAIN,
                scope_id=payload.domain,
                title=feedback or f"处理 {issue_note}",
                content=content,
                evidence=evidence,
                applicability=("writing",),
                tags={payload.domain, "quality", *repeated},
                confidence=min(0.9, 0.4 + 0.1 * max(payload.attempts, 1)),
            )
        )
    return candidates


def _normalize(value: str) -> str:
    return "_".join(value.strip().casefold().split())


def _candidate_id(scope_id: str, content: str) -> str:
    normalized = " ".join(content.casefold().split())
    digest = hashlib.sha256(f"domain|{scope_id}|{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"experience-{digest}"
