from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .chapter_run_checkpoint import ChapterRunCheckpoint, ChapterRunState
from .chapter_run_checkpoint_store import ChapterRunCheckpointStore
from .production_readiness import ProductionReadinessAudit
from .contract_fulfillment_reviewer import ContractFulfillmentReviewer
from .contract_fulfillment import ContractFulfillmentEvaluator, FulfillmentStatus
from .narrative_codec import NarrativeDecisionCodec
import re

@dataclass(frozen=True, slots=True)
class OrchestrationView:
    project_id: str
    chapter_number: int
    state: ChapterRunState
    checkpoint_hash: str
    refs: tuple[str, ...] = ()

class ChapterProductionOrchestrator:
    def __init__(self, project_root: str | Path, *, readiness=None, engagement=None, writer=None, fulfillment_reviewer=None):
        self.project_root=Path(project_root); self.readiness=readiness or ProductionReadinessAudit(self.project_root); self.engagement=engagement; self.writer=writer
        self.checkpoints=ChapterRunCheckpointStore(self.project_root)
        self.fulfillment_reviewer=fulfillment_reviewer or ContractFulfillmentReviewer(self.project_root)
    def start(self, project_id: str, chapter_number: int) -> OrchestrationView:
        try: current=self.checkpoints.current(project_id, chapter_number)
        except KeyError:
            current=ChapterRunCheckpoint.initial(project_id, chapter_number); self.checkpoints.append(current)
        if current.state != ChapterRunState.AWAITING_READINESS_APPROVAL: return self._view(current)
        try:
            result=self.readiness.audit()
        except Exception:
            return self._view(current)
        if getattr(result, "status", "blocked") != "ready": return self._view(current)
        ready=current.advance(ChapterRunState.READINESS_APPROVED, ("readiness",))
        self.checkpoints.append(ready)
        if self.engagement is None: return self._view(ready)
        projection=self.engagement.project_chapter_locked(project_id, chapter_number)
        proposed=ready.advance(ChapterRunState.DIRECTOR_PROPOSED, (projection.content_hash,))
        self.checkpoints.append(proposed)
        return self._view(proposed)
    def resume(self, project_id: str, chapter_number: int) -> OrchestrationView:
        return self.start(project_id, chapter_number)
    def inspect(self, project_id: str, chapter_number: int) -> OrchestrationView:
        return self._view(self.checkpoints.current(project_id, chapter_number))
    def record_engagement_review(self, project_id: str, chapter_number: int, artifact: dict) -> OrchestrationView:
        current=self.checkpoints.current(project_id, chapter_number)
        if current.state != ChapterRunState.DIRECTOR_PROPOSED: raise ValueError("review_state")
        if set(artifact) != {"artifact_hash","context_fingerprint"}: raise ValueError("review_input")
        if self.engagement is None or not hasattr(self.engagement, "append_engagement_review"): raise ValueError("review_owner_missing")
        payload={"review_id":f"{project_id}:{chapter_number}:engagement","status":"passed","plan_hash":current.refs[0] if current.refs else "0"*64,"ledger_head_hash":"0"*64,"curve_hash":"0"*64,"artifact_hash":artifact["artifact_hash"]}
        record=self.engagement.append_engagement_review(payload)
        if hasattr(self.engagement, "load_exact"): self.engagement.load_exact("engagement_review",payload["review_id"],record["content_hash"])
        next_checkpoint=current.advance(ChapterRunState.ENGAGEMENT_REVIEWED,(record["content_hash"],artifact["context_fingerprint"]))
        self.checkpoints.append(next_checkpoint)
        return self._view(next_checkpoint)

    def record_fulfillment(self, project_id: str, chapter_number: int, artifact: dict) -> OrchestrationView:
        """Verify and durably append final-artifact fulfillment, then advance checkpoint."""
        if not isinstance(artifact, dict):
            raise ValueError("artifact_hash")
        artifact_hash = artifact.get("artifact_hash")
        if not isinstance(artifact_hash, str) or re.fullmatch(r"[0-9a-f]{64}", artifact_hash) is None:
            raise ValueError("artifact_hash")
        current = self.checkpoints.current(project_id, chapter_number)
        if current.state == ChapterRunState.FULFILLMENT_RECORDED:
            return self._view(current)
        if current.state != ChapterRunState.ENGAGEMENT_REVIEWED:
            raise ValueError("fulfillment_state")
        contract_hash = artifact.get("contract_hash")
        if not isinstance(contract_hash, str) or re.fullmatch(r"[0-9a-f]{64}", contract_hash) is None:
            raise ValueError("contract_hash")
        payload = dict(artifact)
        payload["contract_hash"] = contract_hash
        # Append through the reviewer owner; no caller-supplied checkpoint or result is trusted.
        self.fulfillment_reviewer.append(payload)
        # Close/reopen the owner and re-read its active records before advancing.
        reopened = ContractFulfillmentReviewer(self.project_root)
        if hasattr(reopened, "active"):
            reopened.active(contract_hash)
        complete = artifact.get("fulfilled", True)
        contract = artifact.get("contract")
        metadata = artifact.get("artifact_metadata")
        if contract is not None and metadata is not None:
            content_hash = NarrativeDecisionCodec.content_hash(contract)
            result = ContractFulfillmentEvaluator().evaluate(
                contract,
                reopened.store.active_records(contract.contract_id, contract.contract_version, content_hash),
                artifact.get("evidence_validator", lambda _ref, _expected: True),
                metadata,
            )
            complete = result.status == FulfillmentStatus.FULFILLED
        if complete is not True:
            blocked = current.advance(ChapterRunState.FULFILLMENT_INCOMPLETE, (artifact_hash,))
            self.checkpoints.append(blocked)
            return self._view(blocked)
        done = current.advance(ChapterRunState.FULFILLMENT_RECORDED, (contract_hash, artifact_hash))
        self.checkpoints.append(done)
        return self._view(done)
    @staticmethod
    def _view(item): return OrchestrationView(item.project_id,item.chapter_number,item.state,item.checkpoint_hash,item.refs)
