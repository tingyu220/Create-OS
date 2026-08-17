from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from creative_os.engine.context import ContextBoundaryError
from creative_os.foundation.knowledge import KnowledgeItem
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task
from creative_os.memory.model import MemoryItem, MemoryKind
from creative_os.memory.retriever import MemoryRetrievalResult


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


class ContextCompiler:
    VERSION = "1"

    def compile(self, request: CompileRequest, *, max_chars: int = 12000) -> CompiledContext:
        self._validate_boundaries(request)
        working = [item for item in request.memory.items if item.kind == MemoryKind.WORKING]
        optional = [item for item in request.memory.items if item.kind != MemoryKind.WORKING]
        selected_memory: list[MemoryItem] = []

        required_size = self._estimate(request, working, request.knowledge, selected_memory)
        if required_size > max_chars:
            raise ContextBoundaryError(f"required context too large: {required_size} > {max_chars}")

        current_size = required_size
        for item in optional:
            item_size = len(item.title) + len(item.content)
            if current_size + item_size > max_chars:
                continue
            selected_memory.append(item)
            current_size += item_size

        sources = self._sources(request, working, selected_memory)
        fingerprint = self._fingerprint(request, working, selected_memory, sources)
        return CompiledContext(
            user_input=request.user_input,
            task=request.task,
            state=request.state,
            working=working,
            knowledge=list(request.knowledge),
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
    ) -> list[ContextSource]:
        sources = [
            ContextSource("knowledge", item.id, "required_project_fact", 1, _hash(item.body))
            for item in request.knowledge
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
    ) -> str:
        payload = {
            "compiler_version": self.VERSION,
            "task_id": request.task.id,
            "state": request.state.compact(),
            "user_input": request.user_input,
            "knowledge": [item.id for item in request.knowledge],
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
