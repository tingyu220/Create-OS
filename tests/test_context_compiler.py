import pytest
import ast
from pathlib import Path

from creative_os.engine.context import ContextBoundaryError
from creative_os.foundation.knowledge import KnowledgeItem
from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task
from creative_os.memory.context_compiler import CompileRequest, ContextCompiler
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope
from creative_os.memory.retriever import MemoryRetrievalResult
from creative_os.domains.writer_admission import AdmittedContractProjection, ContextExclusion
from dataclasses import replace


def _active_memory(item_id: str, kind: MemoryKind, content: str) -> MemoryItem:
    return MemoryItem.new_candidate(
        id=item_id,
        kind=kind,
        scope=MemoryScope.PROJECT if kind == MemoryKind.WORKING else MemoryScope.DOMAIN,
        scope_id="文明升阶" if kind == MemoryKind.WORKING else "novel",
        title=item_id,
        content=content,
        evidence=[MemoryEvidence(source_type="review", source_id=f"source-{item_id}")],
        applicability=("writing",),
    ).activate(actor="tingyu")


def _request(optional_content: str = "保持自然转场") -> CompileRequest:
    task = Task(id="chapter-003", title="续写第三章", kind="writing", domain="novel", goal="延续龙渊剧情")
    state = ProjectState("Draft", task.id, task.goal, "novel")
    required = KnowledgeItem(
        id="required-character-state",
        kind="character_state",
        title="林子轩当前状态",
        body="林子轩已经进入龙渊基地。",
        tags={"林子轩"},
    )
    working = _active_memory("working-current", MemoryKind.WORKING, "上一章结束于主角进入基地。")
    experience = _active_memory("experience-transition", MemoryKind.EXPERIENCE, optional_content)
    return CompileRequest(
        user_input="接着写，不修改核心设定。",
        task=task,
        state=state,
        knowledge=[required],
        memory=MemoryRetrievalResult(
            items=[working, experience],
            reasons={working.id: ["scope:project"], experience.id: ["scope:domain"]},
        ),
        domain_rules=["character_consistency"],
    )


def test_compiler_keeps_required_project_facts_before_optional_experience():
    compiled = ContextCompiler().compile(_request(optional_content="x" * 2000), max_chars=600)

    assert compiled.knowledge[0].id == "required-character-state"
    assert [item.id for item in compiled.working] == ["working-current"]
    assert compiled.memory == []
    assert all(source.source_id for source in compiled.sources)
    assert compiled.size_chars <= 600


def test_compiler_output_is_reproducible_for_same_inputs():
    compiler = ContextCompiler()
    request = _request()

    assert compiler.compile(request).fingerprint == compiler.compile(request).fingerprint


def test_compiler_rejects_required_context_over_budget():
    with pytest.raises(ContextBoundaryError):
        ContextCompiler().compile(_request(), max_chars=20)


def test_projection_is_injected_once_and_all_contract_memory_is_excluded():
    request = _request()
    old = _active_memory("narrative-chapter-003-v0001", MemoryKind.PROJECT_DECISION, "旧合同")
    request = replace(request,
        memory=MemoryRetrievalResult(items=[*request.memory.items, old], reasons={**request.memory.reasons, old.id:["project"]}),
        contract_projection=AdmittedContractProjection("narrative-chapter-003", 1, "a"*64, '{"contract":1}'),
        exclusions=(ContextExclusion("narrative-chapter-003", 1),))
    legacy = KnowledgeItem(id="narrative:chapter:003", kind="narrative_decision",
        title="旧合同", body="旧合同", tags={"narrative"})
    request = replace(request, knowledge=[*request.knowledge, legacy])
    compiled = ContextCompiler().compile(request)
    assert [item.kind for item in compiled.knowledge].count("narrative_decision") == 1
    assert old.id not in [item.id for item in compiled.memory]
    assert legacy.id not in [item.id for item in compiled.knowledge]
    changed = replace(request, contract_projection=replace(request.contract_projection, canonical_json='{"contract":2}'))
    assert ContextCompiler().compile(changed).fingerprint != compiled.fingerprint


def test_continuation_cannot_load_active_contract_or_finalize_admission():
    tree = ast.parse(Path("creative_os/domains/novel_continuation.py").read_text(encoding="utf-8"))
    text = ast.unparse(tree)
    assert "load_active_narrative" not in text
    assert "finalize_admission" not in text
    assert "WriterAdmissionToken" not in text
