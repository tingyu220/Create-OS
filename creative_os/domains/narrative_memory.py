from __future__ import annotations

from pathlib import Path
from typing import Iterable

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import NarrativeChangeRequest, NarrativeDecision, NarrativeProjectProfile
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


def save_project_profile_candidate(
    project_root: str | Path,
    profile: NarrativeProjectProfile,
    *,
    evidence: Iterable[MemoryEvidence],
) -> MemoryItem:
    profile.validate()
    return _save_candidate(
        project_root,
        item_id="narrative-project-profile",
        title="项目叙事承诺与剧情阶段",
        content=profile.to_json(),
        evidence=evidence,
        tags={"novel", "narrative", "narrative_project_profile"},
    )


def load_active_narrative_profile(project_root: str | Path) -> NarrativeProjectProfile | None:
    item = _active_item(project_root, "narrative-project-profile")
    return NarrativeProjectProfile.from_json(item.content) if item else None


def save_narrative_candidate(
    project_root: str | Path,
    decision: NarrativeDecision,
    *,
    evidence: Iterable[MemoryEvidence],
) -> MemoryItem:
    item = build_narrative_candidate_item(
        project_root,
        decision,
        evidence=evidence,
        item_id=f"narrative-chapter-{decision.chapter:03d}",
    )
    JsonMemoryStore(Path(project_root) / ".creative_os" / "memory").add_candidate(item)
    return item


def build_narrative_candidate_item(
    project_root: str | Path,
    decision: NarrativeDecision,
    *,
    evidence: Iterable[MemoryEvidence],
    item_id: str,
) -> MemoryItem:
    """Build one canonical contract envelope without choosing a storage policy."""
    decision.validate()
    root = Path(project_root)
    return MemoryItem.new_candidate(
        id=item_id,
        kind=MemoryKind.PROJECT_DECISION,
        scope=MemoryScope.PROJECT,
        scope_id=root.name,
        title=f"第 {decision.chapter} 章叙事合同",
        content=NarrativeDecisionCodec.encode_v2(decision),
        evidence=tuple(evidence),
        applicability=("writing", "planning", "review"),
        tags={"novel", "narrative", "narrative_decision", f"chapter_{decision.chapter:03d}"},
        confidence=1.0,
    )


def load_active_narrative_decision(project_root: str | Path, chapter_number: int) -> NarrativeDecision | None:
    if chapter_number < 1:
        raise ValueError("chapter_number must be positive")
    item = _active_item(project_root, f"narrative-chapter-{chapter_number:03d}")
    if item is None:
        return None
    decision = NarrativeDecision.from_json(item.content)
    if decision.chapter != chapter_number:
        raise ValueError(f"narrative decision chapter mismatch: {decision.chapter} != {chapter_number}")
    return decision


def save_change_request_candidate(
    project_root: str | Path,
    request: NarrativeChangeRequest,
    *,
    evidence: Iterable[MemoryEvidence],
) -> MemoryItem:
    request.validate()
    return _save_candidate(
        project_root,
        item_id=f"narrative-change-{request.id}",
        title=f"叙事改纲：{request.id}",
        content=request.to_json(),
        evidence=evidence,
        tags={"novel", "narrative", "narrative_change_request"},
    )


def _save_candidate(
    project_root: str | Path,
    *,
    item_id: str,
    title: str,
    content: str,
    evidence: Iterable[MemoryEvidence],
    tags: set[str],
) -> MemoryItem:
    root = Path(project_root)
    item = MemoryItem.new_candidate(
        id=item_id,
        kind=MemoryKind.PROJECT_DECISION,
        scope=MemoryScope.PROJECT,
        scope_id=root.name,
        title=title,
        content=content,
        evidence=tuple(evidence),
        applicability=("writing", "planning", "review"),
        tags=tags,
        confidence=1.0,
    )
    JsonMemoryStore(root / ".creative_os" / "memory").add_candidate(item)
    return item


def _active_item(project_root: str | Path, item_id: str) -> MemoryItem | None:
    root = Path(project_root)
    store = JsonMemoryStore(root / ".creative_os" / "memory")
    try:
        item = store.get(item_id)
    except KeyError:
        return None
    if item.status != MemoryStatus.ACTIVE:
        return None
    if item.kind != MemoryKind.PROJECT_DECISION or item.scope != MemoryScope.PROJECT or item.scope_id != root.name:
        return None
    return item
