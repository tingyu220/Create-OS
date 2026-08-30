from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from creative_os.domains.novel_compile_model import (
    CanonPatch,
    NovelCompileRequest,
    NovelCompileResult,
    NovelNextTaskInput,
)
from creative_os.domains.novel_state_model import StateChange, StateEvidence


class NovelCompileError(ValueError):
    """通过稿无法安全编译为小说领域候选。"""


class NovelCompiler:
    """把通过稿编译为候选，不直接写入 Canon 或状态仓库。"""

    def compile(self, request: NovelCompileRequest) -> NovelCompileResult:
        if not request.review.passed:
            raise NovelCompileError("review_not_passed")
        if not request.chapter_id.strip() or not request.source_chapter.strip() or not request.draft.strip():
            raise NovelCompileError("compile_request_invalid")
        actual_hash = hashlib.sha256(request.draft.encode("utf-8")).hexdigest()
        if actual_hash != request.content_hash:
            raise NovelCompileError("draft_hash_mismatch")
        request.chapter_contract.scene_plan.validate(required=True, novel_required=True)

        canon_patches: list[CanonPatch] = []
        state_changes: list[StateChange] = []
        resulting_states: list[str] = []
        for scene in request.chapter_contract.scene_plan.scenes:
            evidence = tuple(StateEvidence(request.source_chapter, item) for item in scene.essential_information)
            canon_patches.append(CanonPatch(
                kind="story_fact",
                subject=scene.id,
                fields={
                    "narrative_purpose": scene.narrative_purpose,
                    "essential_information": scene.essential_information,
                    "outcome": scene.state_change,
                },
                evidence=evidence,
            ))
            event_id = _stable_id(request.chapter_id, "event", scene.id)
            state_changes.append(StateChange(
                id=event_id,
                kind="event",
                subject=scene.id,
                status="candidate",
                fields={
                    "action": scene.action,
                    "information_change": scene.information_change,
                    "state_change": scene.state_change,
                },
                evidence=list(evidence),
            ))
            state_changes.append(StateChange(
                id=_stable_id(request.chapter_id, "timeline", scene.id),
                kind="timeline",
                subject=f"{request.chapter_id}:{scene.order}",
                status="candidate",
                fields={"relative_order": scene.order, "time_window": scene.time_window},
                evidence=list(evidence),
            ))
            resulting_states.append(scene.state_change)

        for proposal in request.character_changes:
            proposal.validate()
            if not proposal.evidence:
                raise NovelCompileError("character_change_evidence_missing")
            state_changes.append(StateChange(
                id=_stable_id(request.chapter_id, "character", proposal.subject),
                kind="character",
                subject=proposal.subject,
                status="candidate",
                fields={"change": proposal.change},
                evidence=[StateEvidence(request.source_chapter, item) for item in proposal.evidence],
            ))
            resulting_states.append(f"{proposal.subject}:{proposal.change}")

        next_task_input = NovelNextTaskInput(
            previous_chapter_id=request.chapter_id,
            previous_chapter_hash=request.content_hash,
            resulting_states=tuple(resulting_states),
            required_open_hooks=tuple(request.chapter_contract.foreshadow_actions.values),
        )
        payload = {
            "canon_patches": [asdict(item) for item in canon_patches],
            "state_changes": [asdict(item) for item in state_changes],
            "next_task_input": asdict(next_task_input),
        }
        fingerprint = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return NovelCompileResult(
            canon_patches=tuple(canon_patches),
            state_changes=tuple(state_changes),
            next_task_input=next_task_input,
            fingerprint=fingerprint,
        )


def _stable_id(chapter_id: str, kind: str, subject: str) -> str:
    digest = hashlib.sha256(f"{chapter_id}:{kind}:{subject}".encode("utf-8")).hexdigest()[:16]
    return f"{chapter_id}-{kind}-{digest}"
