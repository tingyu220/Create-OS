"""从原任务取战斗建议，合入故事候选；来源关联与故事版本原子提交。"""

from copy import deepcopy
from creative_os.combat_context import read_combat_source
from creative_os.combat_model import CombatRequest, CombatScope, CombatResult
from creative_os.domains.project_authority import project_authority_lock
from creative_os.project_directory import validated_project
from creative_os.story_architecture_store import content_hash, validate_content
from creative_os.writer_context_sources import digest


PLAN_FIELDS = {"block_key", "result_id", "project_id", "scope", "evidence_refs", "source_hashes",
               "result_hash", "original_block_hash", "author_revised", "evidence_basis"}


def validate_combat_plans(plans, blocks, project_id=None):
    """机器来源只存在结构化关联中，不能通过正文伪造。"""
    if not isinstance(plans, list) or len(plans) > len(blocks):
        raise ValueError("combat_plans_invalid")
    keys, seen = {block["key"] for block in blocks}, set()
    for plan in plans:
        if not isinstance(plan, dict) or set(plan) != PLAN_FIELDS:
            raise ValueError("combat_plans_invalid")
        key, result_id = plan["block_key"], plan["result_id"]
        if (not isinstance(result_id, str) or not result_id.strip()
                or key != "combat-plan:" + result_id or key not in keys or key in seen
                or not isinstance(plan["project_id"], str) or not plan["project_id"].strip()
                or (project_id is not None and plan["project_id"] != project_id)
                or type(plan["author_revised"]) is not bool or plan["evidence_basis"] != "expert_original"):
            raise ValueError("combat_plans_invalid")
        scope = plan["scope"]
        if not isinstance(scope, dict) or set(scope) != {"chapter_numbers", "purpose"} or not isinstance(scope["chapter_numbers"], list):
            raise ValueError("combat_plans_invalid")
        CombatScope(tuple(scope["chapter_numbers"]), scope["purpose"])
        refs, hashes = plan["evidence_refs"], plan["source_hashes"]
        if (not isinstance(refs, list) or any(not isinstance(ref, str) or not ref for ref in refs)
                or len(set(refs)) != len(refs) or not isinstance(hashes, dict) or set(hashes) != set(refs)):
            raise ValueError("combat_plans_invalid")
        for value in [plan["result_hash"], plan["original_block_hash"], *hashes.values()]:
            if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError("combat_plans_invalid")
        seen.add(key)
    return deepcopy(plans)


def reconcile_combat_plans(content, blocks, actor):
    """编辑保留原建议的来源；删块同步去关联，修订不继承证据背书。"""
    current = {block["key"]: block for block in blocks}
    plans = []
    for plan in content.get("combat_plans", []):
        if plan["block_key"] not in current:
            continue
        plan = deepcopy(plan)
        revised = content_hash(current[plan["block_key"]]) != plan["original_block_hash"]
        plan["author_revised"] = plan["author_revised"] or (revised and actor == "作者")
        plans.append(plan)
    return plans


def _load_result(store, result_id):
    # 只读原会话存储，不装配 Runtime，也不触发中断恢复。
    from creative_os.agent_conversation_store import AgentConversationStore
    if not isinstance(result_id, str) or not result_id.strip():
        raise ValueError("combat_result_id_required")
    selected, _ = validated_project(store.root.parent, store.project_id)
    if selected != store.root.resolve():
        raise ValueError("combat_project_scope_mismatch")
    jobs = AgentConversationStore(store.root, store.project_id).load_jobs()
    matches = [(job, result) for job in jobs for result in job.get("combat_results", [])
               if result.get("result_id") == result_id]
    if len(matches) != 1:
        raise ValueError("combat_result_not_found_or_ambiguous")
    job, value = matches[0]
    if (job.get("project_id") != store.project_id or value.get("project_id") != store.project_id
            or value.get("job_id") != job["job_id"] or job.get("mode") != "analyze"):
        raise ValueError("combat_result_scope_mismatch")
    frozen = deepcopy(job.get("combat_context"))
    if (not isinstance(frozen, dict) or frozen.get("project_id") != store.project_id
            or frozen.get("session_id") != job.get("session_id") or value.get("scope") != frozen.get("scope")):
        raise ValueError("combat_result_scope_mismatch")
    # 重试结果属于本次任务，冻结证据仍绑定原任务；仅接受真实重试祖先。
    ancestors, current = set(), job
    while current is not None and current["job_id"] not in ancestors:
        if current.get("project_id") != store.project_id or current.get("session_id") != job["session_id"]:
            raise ValueError("combat_result_scope_mismatch")
        ancestors.add(current["job_id"])
        current = next((item for item in jobs if item["job_id"] == current.get("retry_of")), None)
    if frozen.get("job_id") not in ancestors:
        raise ValueError("combat_result_scope_mismatch")
    scope = CombatScope(tuple(frozen["scope"]["chapter_numbers"]), frozen["scope"]["purpose"])
    request = CombatRequest(**{**frozen, "scope": scope, "sources": tuple(frozen["sources"])})
    CombatResult(**{**value, "scope": scope})
    if not isinstance(value.get("reply"), str) or not value["reply"].strip():
        raise ValueError("combat_result_invalid")
    for field in ("alternatives", "foreshadowing", "evidence_refs", "unknowns"):
        if not isinstance(value.get(field), list) or any(not isinstance(item, str) for item in value[field]):
            raise ValueError("combat_result_invalid")
    hashes = {}
    for ref in value["evidence_refs"]:
        source = read_combat_source(request, ref)
        if source.get("usage") != "included" or source.get("hash") != digest(source.get("text", "")):
            raise ValueError("combat_evidence_invalid")
        hashes[ref] = source["hash"]
    return deepcopy(value), hashes


def _suggestion_block(result):
    sections = ["未来创作计划：以下为建议，不是已发生事实。", result["reply"]]
    for field, title in (("alternatives", "备选方案"), ("foreshadowing", "铺垫建议"), ("unknowns", "仍未知")):
        if result[field]:
            sections.append(title + "：\n" + "\n".join("- " + item for item in result[field]))
    return {"key": "combat-plan:" + result["result_id"], "title": "战斗编排建议（未来计划）", "text": "\n\n".join(sections)}


def stage_combat_candidate(store, result, *, expected_revision, actor, operation_id) -> dict:
    """result 仅为结果 ID；所有结果内容和来源均从服务端任务重读。"""
    if type(expected_revision) is not int or expected_revision < 0 or not isinstance(actor, str) or not actor.strip():
        raise ValueError("story_revision_invalid")
    with project_authority_lock(store.root):
        value, hashes = _load_result(store, result)
        data = store._read()
        fingerprint, previous = store._operation(data, store.session_id, operation_id,
            {"action": "adopt_combat", "result_id": result, "result_hash": content_hash(value),
             "expected_revision": expected_revision, "actor": actor})
        if previous is not None:
            return previous
        base = (data["revisions"][-1] if data["revisions"] else
                data["confirmed_versions"][-1] if data["current"] else None)
        content = deepcopy(base["content"]) if base else {"blocks": [], "open_questions": ["其他正式设定尚缺，需作者补充并明确确认。"]}
        block = _suggestion_block(value)
        content["blocks"] = [block if item["key"] == block["key"] else item for item in content["blocks"]]
        if not any(item["key"] == block["key"] for item in content["blocks"]):
            content["blocks"].append(block)
        plans = [item for item in content.get("combat_plans", []) if item["block_key"] != block["key"]]
        plans.append({"block_key": block["key"], "result_id": result, "project_id": store.project_id,
                      "scope": value["scope"], "evidence_refs": list(dict.fromkeys(value["evidence_refs"])), "source_hashes": hashes,
                      "result_hash": content_hash(value), "original_block_hash": content_hash(block),
                      "author_revised": False, "evidence_basis": "expert_original"})
        content = validate_content(content["blocks"], content["open_questions"], plans)
        return store._append_candidate(data, content, expected_revision, actor, operation_id, fingerprint)
