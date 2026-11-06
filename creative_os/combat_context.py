"""按书冻结有限证据；来源查询只消费快照，不把引用解释为路径。"""

from copy import deepcopy
import json
from pathlib import Path

from creative_os.combat_model import CombatRequest, CombatScope
from creative_os.project_directory import read_project_metadata
from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.writer_context_sources import digest


SOURCE_LIMIT = 12000
TOTAL_LIMIT = 48000


def _safe_path(root, relative):
    path = root / relative
    # 与项目目录规则一致：包括中间目录在内，禁止通过链接访问其他身份。
    if path.resolve() != path.absolute():
        raise ValueError("combat_source_scope_mismatch")
    return path


def _source_id(request, index):
    identity = json.dumps([request.project_id, request.session_id, request.job_id], ensure_ascii=False)
    return f"combat-source-{digest(identity)}-{index:04d}"


def build_combat_context(root, project_id, scope, *, task_id, session_id, instruction) -> CombatRequest:
    """冻结文件证据；root 须先由 registry / validated_project 选定。

    本函数只校验具名根的元数据身份，不重复扫描项目集合或判断全局身份冲突。
    消费方不得修改请求中的嵌套字段。
    """
    root = Path(root).absolute()
    metadata = read_project_metadata(root.parent, root)
    if metadata["id"] != project_id:
        raise ValueError("combat_project_scope_mismatch")
    if (not isinstance(scope, CombatScope)
            or any(not isinstance(value, str) or not value.strip() for value in (task_id, session_id, instruction))):
        raise ValueError("combat_request_invalid")
    sources, total = [], 0

    def add(kind, chapter_number, ref, text=None, *, version=None, role="reference", reason=None, required=True):
        nonlocal total
        source = {"kind": kind, "chapter_number": chapter_number, "source_ref": ref,
                  "project_id": project_id, "session_id": session_id, "job_id": task_id,
                  "role": role, "version": version, "usage": "missing" if text is None else "included"}
        if text is not None:
            if len(text) > SOURCE_LIMIT or total + len(text) > TOTAL_LIMIT:
                if required:
                    raise ValueError("required_combat_context_budget_exceeded: 请缩小范围后重试")
                source.update(usage="not_read", reason="budget_exceeded")
            else:
                total += len(text)
                source.update(text=text, hash=digest(text), original_chars=len(text),
                              excerpt_start=0, excerpt_end=len(text), truncated=False)
        elif reason:
            source["reason"] = reason
        sources.append(source)

    _safe_path(root, ".creative_os/story/architecture.json")
    story = StoryArchitectureStore(root, project_id).view()
    confirmed = story["confirmed"]
    frozen_story = None
    if confirmed is not None:
        add("confirmed_story", None, ".creative_os/story/architecture.json#confirmed", confirmed["text"],
            version=confirmed["version"])
        frozen_story = {**deepcopy(confirmed), "project_id": project_id}
    else:
        add("confirmed_story", None, ".creative_os/story/architecture.json#confirmed", reason="not_confirmed")

    for number in scope.chapter_numbers:
        draft_ref = f".creative_os/writer/drafts/chapter_{number:03d}.jsonl"
        path = _safe_path(root, draft_ref)
        records = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        record = json.loads(next((line for line in reversed(records) if line.strip()), "null"))
        if record is not None and (not isinstance(record, dict) or not isinstance(record.get("content"), str)
                                   or type(record.get("version")) is not int or record["version"] <= 0):
            raise ValueError("combat_draft_invalid")
        add("working_draft", number, draft_ref, record["content"] if record else None,
            version=record["version"] if record else None, role="target", reason="target_draft_missing")
        formal_ref = f"production/final_chapters/chapter_{number:03d}.md"
        path = _safe_path(root, formal_ref)
        add("written_chapter", number, formal_ref, path.read_text(encoding="utf-8") if path.is_file() else None,
            role="target", reason="target_formal_missing")

    # 固定相邻章，不枚举全书；空范围保持全书研究语义，绝不隐式读取全部正文。
    neighbors = sorted({other for number in scope.chapter_numbers for other in (number - 1, number + 1)
                        if other > 0 and other not in scope.chapter_numbers})
    for number in neighbors[:2]:
        ref = f"production/final_chapters/chapter_{number:03d}.md"
        path = _safe_path(root, ref)
        if path.is_file():
            add("written_chapter", number, ref, path.read_text(encoding="utf-8"), role="adjacent", required=False)
    candidate = story["candidate"]
    if candidate is not None and (confirmed is None or candidate["hash"] != confirmed["hash"]):
        add("story_candidate", None, ".creative_os/story/architecture.json#candidate", candidate["text"],
            version=candidate["revision"], reason="unconfirmed_plan", required=False)
        sources[-1]["semantics"] = "未确认规划，不是已发生事实或正式设定"
    request = CombatRequest(project_id, session_id, task_id, instruction, scope, frozen_story, tuple(sources))
    for index, source in enumerate(sources, 1):
        source["source_id"] = _source_id(request, index)
    return request


def read_combat_source(snapshot, source_id) -> dict:
    if not isinstance(snapshot, CombatRequest) or not isinstance(source_id, str):
        raise ValueError("combat_source_invalid")
    for index, source in enumerate(snapshot.sources, 1):
        if source.get("source_id") == source_id:
            if (source_id != _source_id(snapshot, index)
                    or any(source.get(key) != getattr(snapshot, key) for key in ("project_id", "session_id", "job_id"))):
                raise ValueError("combat_source_scope_mismatch")
            return deepcopy(source)
    raise ValueError("combat_source_not_found")
