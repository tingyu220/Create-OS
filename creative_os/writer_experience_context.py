"""通过现有检索器和预算编译器选入已批准的项目写作经验。"""

from dataclasses import asdict, replace
import json

from creative_os.foundation.state import ProjectState
from creative_os.foundation.task import Task
from creative_os.memory.context_compiler import CompileRequest, ContextCompiler
from creative_os.memory.model import MemoryKind, MemoryScope
from creative_os.memory.retriever import MemoryQuery, MemoryRetriever, MemoryRetrievalResult
from creative_os.memory.store import JsonMemoryStore
from creative_os.writer_lesson import digest


def compile_writer_experience(root, project_id, chapter, task_id, *, max_chars=4000):
    trace = {"schema_version": 1, "budget_chars": max_chars, "selected": [], "excluded": [],
             "rendered_chars": 0, "truncated": False}
    if not (root / ".creative_os/memory/items").exists():
        return "", trace
    store = JsonMemoryStore(root / ".creative_os/memory")
    result = MemoryRetriever().retrieve(
        MemoryQuery(task_id, project_id, "作者", "novel", "writing", {"writer_lesson", "lesson"}),
        [store], limit=10000)
    eligible, originals = [], {}
    for item in result.items:
        if item.kind != MemoryKind.EXPERIENCE or item.scope != MemoryScope.PROJECT or "writer_lesson" not in item.tags:
            continue
        body = json.loads(item.content)
        if body["feedback"]["project_id"] != project_id:
            continue
        if body["range"] != "project" and body["chapter_number"] != chapter:
            trace["excluded"].append({"memory_id": item.id, "reason": "chapter_scope_mismatch"})
            continue
        scope = "本项目" if body["range"] == "project" else f"第{chapter}章"
        text = f"【{item.title}；适用：{scope}；来源：{item.id} v{item.version}】\n{body['content']}\n"
        eligible.append(replace(item, content=text))
        originals[item.id] = item
    task = Task(task_id, "", "writing", "novel", "")
    state = ProjectState("writing", task_id, "", "novel")
    compiled = ContextCompiler().compile(CompileRequest(
        "", task, state, [], MemoryRetrievalResult(eligible, result.reasons), []), max_chars=max_chars)
    selected_ids = {item.id for item in compiled.memory}
    for item in eligible:
        if item.id not in selected_ids:
            trace["excluded"].append({"memory_id": item.id, "reason": "budget_exceeded", "content_chars": len(item.content)})
    for rendered in compiled.memory:
        original = originals[rendered.id]
        trace["selected"].append({"memory_id": original.id, "version": original.version,
                                  "scope_id": original.scope_id, "approved_by": original.approved_by,
                                  "source_ref": f"memory:{original.id}:v{original.version}",
                                  "content_snapshot": rendered.content, "content_hash": digest(rendered.content),
                                  "memory_content_snapshot": original.content, "memory_content_hash": digest(original.content),
                                  "evidence": [asdict(value) for value in original.evidence],
                                  "reasons": result.reasons[original.id], "truncated": False})
    prompt = "\n".join(item.content for item in compiled.memory)
    trace.update(rendered_chars=len(prompt), compiler_fingerprint=compiled.fingerprint,
                 compiler_version=compiled.compiler_version,
                 truncated=any(item["reason"] == "budget_exceeded" for item in trace["excluded"]))
    return prompt, trace
