from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from typing import Protocol

from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from creative_os.domains.narrative_decision import (
    ChapterContract,
    NarrativeDecision,
    NarrativeValidationError,
)


class NovelWritingError(ValueError):
    """Writer 未能生成与准入绑定的正文。"""


@dataclass(frozen=True, slots=True)
class NovelWritingRequest:
    chapter_id: str
    chapter_contract: ChapterContract
    context_fingerprint: str
    instruction: str
    contract_id: str
    contract_content_hash: str
    chapter_contract_hash: str
    contract_canonical_json: str

    def __post_init__(self) -> None:
        if self.chapter_contract.chapter_id != self.chapter_id:
            raise NovelWritingError("novel_writer_request_chapter_mismatch")
        try:
            projected = NarrativeDecisionCodec.decode(self.contract_canonical_json)
            canonical_json = NarrativeDecisionCodec.encode(projected)
        except (NarrativeValidationError, TypeError, ValueError) as error:
            raise NovelWritingError("novel_writer_request_contract_projection_invalid") from error
        if canonical_json != self.contract_canonical_json:
            raise NovelWritingError("novel_writer_request_contract_projection_invalid")
        if NarrativeDecisionCodec.content_hash(projected) != self.contract_content_hash:
            raise NovelWritingError("novel_writer_request_contract_hash_mismatch")
        if projected.contract_id != self.contract_id:
            raise NovelWritingError("novel_writer_request_contract_id_mismatch")
        if projected.chapter_contract.chapter_id != self.chapter_id:
            raise NovelWritingError("novel_writer_request_chapter_mismatch")
        if projected.chapter_contract != self.chapter_contract:
            raise NovelWritingError("novel_writer_request_contract_projection_mismatch")
        if (
            chapter_contract_content_hash(self.chapter_contract) != self.chapter_contract_hash
            or chapter_contract_content_hash(projected.chapter_contract) != self.chapter_contract_hash
        ):
            raise NovelWritingError("novel_writer_request_chapter_contract_hash_mismatch")

    @classmethod
    def from_narrative_decision(
        cls,
        decision: NarrativeDecision,
        *,
        context_fingerprint: str,
        instruction: str,
    ) -> "NovelWritingRequest":
        """从权威 NarrativeDecision 投影构造不可漂移的 Writer 请求。"""
        canonical_json = NarrativeDecisionCodec.encode(decision)
        return cls(
            chapter_id=decision.chapter_contract.chapter_id,
            chapter_contract=decision.chapter_contract,
            context_fingerprint=context_fingerprint,
            instruction=instruction,
            contract_id=decision.contract_id,
            contract_content_hash=NarrativeDecisionCodec.content_hash(decision),
            chapter_contract_hash=chapter_contract_content_hash(decision.chapter_contract),
            contract_canonical_json=canonical_json,
        )


@dataclass(frozen=True, slots=True)
class NovelDraft:
    content: str
    content_hash: str

    @classmethod
    def from_content(cls, content: str) -> "NovelDraft":
        normalized = content.strip()
        if not normalized:
            raise NovelWritingError("novel_draft_empty")
        return cls(normalized, hashlib.sha256(normalized.encode("utf-8")).hexdigest())


class NovelWriterPort(Protocol):
    def write(self, request: NovelWritingRequest, admission: object) -> NovelDraft: ...


def chapter_contract_content_hash(chapter_contract: ChapterContract) -> str:
    """生成章节合同的稳定哈希，供请求与权威投影分别复算。"""
    if not isinstance(chapter_contract, ChapterContract):
        raise NovelWritingError("novel_writer_request_chapter_contract_invalid")
    canonical = json.dumps(
        asdict(chapter_contract),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_novel_writing_admission_binding(
    request: NovelWritingRequest,
    admission: object,
) -> None:
    """校验准入令牌与请求中的权威合同投影完全一致。"""
    if request.chapter_contract.chapter_id != request.chapter_id:
        raise NovelWritingError("novel_writer_request_chapter_mismatch")
    if getattr(admission, "chapter_id", None) != request.chapter_id:
        raise NovelWritingError("novel_writer_chapter_binding_mismatch")
    if getattr(admission, "context_fingerprint", None) != request.context_fingerprint:
        raise NovelWritingError("novel_writer_context_binding_mismatch")
    contract_id = getattr(admission, "contract_id", None)
    if not isinstance(contract_id, str) or not contract_id.strip():
        raise NovelWritingError("novel_writer_contract_id_missing")
    if contract_id != request.contract_id:
        raise NovelWritingError("novel_writer_contract_id_binding_mismatch")
    if getattr(admission, "contract_content_hash", None) != request.contract_content_hash:
        raise NovelWritingError("novel_writer_contract_hash_binding_mismatch")
