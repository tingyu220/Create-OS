from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from creative_os.engine.context import ContextBoundaryError
from creative_os.foundation.knowledge import KnowledgeItem
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task
from creative_os.memory.model import MemoryItem, MemoryKind
from creative_os.memory.retriever import MemoryRetrievalResult
from creative_os.domains.writer_admission import AdmittedContractProjection, ContextExclusion


@dataclass(frozen=True, slots=True)
class ContextSource:
    source_type: str
    source_id: str
    reason: str
    version: int
    content_hash: str


@dataclass(frozen=True, slots=True)
class CompileRequest:
    user_input: str
    task: Task
    state: ProjectState
    knowledge: list[KnowledgeItem]
    memory: MemoryRetrievalResult
    domain_rules: list[str]
    contract_projection: AdmittedContractProjection | None = None
    exclusions: tuple[ContextExclusion, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledContext:
    user_input: str
    task: Task
    state: ProjectState
    working: list[MemoryItem]
    knowledge: list[KnowledgeItem]
    memory: list[MemoryItem]
    rules: list[str]
    sources: list[ContextSource]
    size_chars: int
    compiler_version: str
    fingerprint: str

    def contains_source(self, source_id: str) -> bool:
        return any(source.source_id == source_id for source in self.sources)


class ContextCompiler:
    VERSION = "1"

    def compile(self, request: CompileRequest, *, max_chars: int = 12000) -> CompiledContext:
        self._validate_boundaries(request)
        working = [item for item in request.memory.items if item.kind == MemoryKind.WORKING]
        excluded = {item.contract_id for item in request.exclusions}
        working = [item for item in working if not _excluded_contract(item.id, excluded)]
        optional = [item for item in request.memory.items if item.kind != MemoryKind.WORKING
                    and not _excluded_contract(item.id, excluded)]
        knowledge = list(request.knowledge)
        if request.contract_projection is not None:
            projection = request.contract_projection
            knowledge = [item for item in knowledge if item.kind != "narrative_decision"
                         and not _excluded_contract(item.id, {projection.contract_id})]
            knowledge.append(KnowledgeItem(
                id=f"{projection.contract_id}-v{projection.contract_version:04d}", kind="narrative_decision",
                title="冻结章节合同", body=projection.canonical_json,
                tags={"narrative", "narrative_decision", "admitted"},
            ))
        selected_memory: list[MemoryItem] = []

        required_size = self._estimate(request, working, knowledge, selected_memory)
        if required_size > max_chars:
            raise ContextBoundaryError(f"required context too large: {required_size} > {max_chars}")

        current_size = required_size
        for item in optional:
            item_size = len(item.title) + len(item.content)
            if current_size + item_size > max_chars:
                continue
            selected_memory.append(item)
            current_size += item_size

        sources = self._sources(request, working, selected_memory, knowledge)
        fingerprint = self._fingerprint(request, working, selected_memory, sources, knowledge)
        return CompiledContext(
            user_input=request.user_input,
            task=request.task,
            state=request.state,
            working=working,
            knowledge=knowledge,
            memory=selected_memory,
            rules=list(request.domain_rules),
            sources=sources,
            size_chars=current_size,
            compiler_version=self.VERSION,
            fingerprint=fingerprint,
        )

    def _validate_boundaries(self, request: CompileRequest) -> None:
        if request.task.id != request.state.current_task_id:
            raise ContextBoundaryError("task does not match project state")
        if request.task.domain != request.state.active_domain:
            raise ContextBoundaryError("task domain does not match project state")

    def _estimate(
        self,
        request: CompileRequest,
        working: list[MemoryItem],
        knowledge: list[KnowledgeItem],
        memory: list[MemoryItem],
    ) -> int:
        task_size = len(request.task.title) + len(request.task.goal) + len(request.task.kind) + len(request.task.domain)
        state_size = sum(len(str(value)) for value in request.state.compact().values())
        knowledge_size = sum(len(item.title) + len(item.body) for item in knowledge)
        memory_size = sum(len(item.title) + len(item.content) for item in [*working, *memory])
        return len(request.user_input) + task_size + state_size + knowledge_size + memory_size + sum(map(len, request.domain_rules))

    def _sources(
        self,
        request: CompileRequest,
        working: list[MemoryItem],
        memory: list[MemoryItem],
        knowledge: list[KnowledgeItem],
    ) -> list[ContextSource]:
        sources = [
            ContextSource("knowledge", item.id, "required_project_fact", 1, _hash(item.body))
            for item in knowledge
        ]
        for item in [*working, *memory]:
            reason = ",".join(request.memory.reasons.get(item.id, [])) or "selected_memory"
            sources.append(ContextSource("memory", item.id, reason, item.version, _hash(item.content)))
        return sources

    def _fingerprint(
        self,
        request: CompileRequest,
        working: list[MemoryItem],
        memory: list[MemoryItem],
        sources: list[ContextSource],
        knowledge: list[KnowledgeItem],
    ) -> str:
        payload = {
            "compiler_version": self.VERSION,
            "task_id": request.task.id,
            "state": request.state.compact(),
            "user_input": request.user_input,
            "knowledge": [item.id for item in knowledge],
            "contract_projection": asdict(request.contract_projection) if request.contract_projection else None,
            "exclusions": [asdict(item) for item in request.exclusions],
            "working": [item.id for item in working],
            "memory": [item.id for item in memory],
            "rules": request.domain_rules,
            "sources": [
                [source.source_type, source.source_id, source.version, source.content_hash]
                for source in sources
            ],
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


def _hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _excluded_contract(item_id: str, contract_ids: set[str]) -> bool:
    return any(item_id == contract_id or item_id.startswith(contract_id + "-v") for contract_id in contract_ids)
