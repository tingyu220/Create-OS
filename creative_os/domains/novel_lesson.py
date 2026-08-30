from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import re

from creative_os.domains.novel_review_model import NovelReviewIssue


_HASH_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class NovelLessonCandidate:
    failure_code: str
    context_fingerprint: str
    repair_action: str
    before_hash: str
    after_hash: str
    issue_evidence: tuple[str, ...]
    validation_evidence: tuple[str, ...]
    status: str = "candidate"
    candidate_hash: str = ""


def build_lesson_candidate(
    *,
    issue: NovelReviewIssue | None,
    context_fingerprint: str,
    repair_action: str,
    before_hash: str,
    after_hash: str,
    validation_evidence: tuple[str, ...],
) -> NovelLessonCandidate:
    if not isinstance(issue, NovelReviewIssue):
        raise ValueError("lesson_evidence_incomplete")
    issue.validate()
    hashes = (context_fingerprint, before_hash, after_hash)
    if any(_HASH_PATTERN.fullmatch(value) is None for value in hashes):
        raise ValueError("lesson_evidence_incomplete")
    if before_hash == after_hash or not repair_action.strip():
        raise ValueError("lesson_evidence_incomplete")
    if not validation_evidence or any(not item.strip() for item in validation_evidence):
        raise ValueError("lesson_evidence_incomplete")
    candidate = NovelLessonCandidate(
        failure_code=issue.code,
        context_fingerprint=context_fingerprint,
        repair_action=repair_action,
        before_hash=before_hash,
        after_hash=after_hash,
        issue_evidence=issue.evidence,
        validation_evidence=validation_evidence,
    )
    payload = asdict(candidate)
    payload.pop("candidate_hash")
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return NovelLessonCandidate(**{**payload, "candidate_hash": digest})


class NovelLessonBuilder:
    def build(self, **kwargs) -> NovelLessonCandidate:
        return build_lesson_candidate(**kwargs)
