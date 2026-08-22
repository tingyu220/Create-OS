from __future__ import annotations

import hashlib
from dataclasses import dataclass

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NarrativeDecision


@dataclass(frozen=True, slots=True)
class MigrationLoss:
    code: str
    field_path: str
    detail: str


@dataclass(frozen=True, slots=True)
class MigrationReport:
    idempotency_key: str
    source_item_id: str
    source_version: int
    source_content_hash: str
    candidate: NarrativeDecision | None
    losses: tuple[MigrationLoss, ...]
    requires_manual_review: bool
    replay_only: bool


class LegacyNarrativeAdapter:
    """Pure v1-to-v2 normalization. It performs no writes or approvals."""

    @classmethod
    def adapt(cls, legacy_item_id: str, legacy_version: int,
              legacy_content_hash: str, content: str, *,
              completed: bool = False) -> MigrationReport:
        if not isinstance(legacy_item_id, str) or not legacy_item_id.strip():
            raise ValueError("legacy_item_id is required")
        if type(legacy_version) is not int or legacy_version < 1:
            raise ValueError("legacy_version must be positive")
        if (not isinstance(legacy_content_hash, str) or len(legacy_content_hash) != 64
                or any(ch not in "0123456789abcdef" for ch in legacy_content_hash)):
            raise ValueError("legacy content hash must be lowercase sha256")
        if not isinstance(content, str):
            raise TypeError("legacy content must be text")
        actual = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if actual != legacy_content_hash:
            raise ValueError("legacy content hash drift")
        key = hashlib.sha256(
            f"{legacy_item_id}\0{legacy_version}\0{legacy_content_hash}".encode()
        ).hexdigest()
        decision = NarrativeDecisionCodec.decode_v1(content)
        losses = [MigrationLoss(
            "derived_chapter_id", "chapter_contract.chapter_id",
            "chapter_id was derived from legacy chapter and is not evidence",
        )]
        if decision.legacy_unclassified_evidence:
            losses.append(MigrationLoss(
                "legacy_unclassified_evidence", "legacy_unclassified_evidence",
                "legacy evidence cannot satisfy v2 admission",
            ))
        nullable = (
            ("chapter_contract.information.misdirect", decision.chapter_contract.information.misdirect),
            ("chapter_contract.foreshadow_actions", decision.chapter_contract.foreshadow_actions),
            ("chapter_contract.forbidden", decision.chapter_contract.forbidden),
        )
        for path, value in nullable:
            if not value.values and value.not_applicable_reason is None:
                losses.append(MigrationLoss(
                    "empty_nullable_plan_requires_review", path,
                    "legacy empty array is not an approved N/A declaration",
                ))
        return MigrationReport(
            key, legacy_item_id.strip(), legacy_version, legacy_content_hash,
            None if completed else decision, tuple(losses), True, completed,
        )
