"""主 Agent 的有限讨论工具及只读专家桥接；不创建客户端或队列。"""

from copy import deepcopy
from dataclasses import asdict
import json

from creative_os.combat_agent import run_combat_expert
from creative_os.combat_context import build_combat_context, read_combat_source
from creative_os.combat_model import CombatRequest, CombatScope
from creative_os.llm_writer import ModelMessage
from creative_os.project_directory import validated_project
from creative_os.writer_context_sources import ContextCapture


MAX_STEPS = 6
MAX_INPUT_CHARS = 100000
PROTOCOL = """章节写作模式必须先完成前置冲突判断：同时检查本章前后文正在升级的冲突、历史遗留但尚未解决的矛盾、以及本章是否需要行动链和代价安排。
至少有一项形成明确的行动或对抗需求时才调用战斗编排专家；只有背景提及、普通对话、过渡、调查或情感章节不得为了凑场景而调用专家。
证据不足时保留未知并继续普通写作，不把关键词命中当作战斗证据。
分析模式同样可自主决定是否需要战斗编排专家。
每次至多输出一个工具 JSON：{"action":"consult_combat"} 或 {"action":"finish","reply":"给作者的自然语言分析"}。
每轮最多委派一次，不能递归。专家结果仅是建议，无权确认、发布或修改正文。保留普通自然语言分析输出的兼容性。"""


def freeze_combat_request(root, project_id, job, *, original=None):
    if original is not None:
        return deepcopy(original.combat_context)
    # 旧无 metadata 的临时/传统入口保持普通分析兼容，不能获得专家读权限。
    if not (root / "project.json").exists():
        if job.requested_expert:
            raise ValueError("combat_project_identity_required")
        return None
    selected, _ = validated_project(root.parent, project_id)
    if selected != root.resolve():
        raise ValueError("combat_project_scope_mismatch")
    scope = CombatScope(() if job.chapter_number is None else (job.chapter_number,), "本轮故事研究" if job.chapter_number is None else "目标章节冲突研究")
    try:
        frozen = build_combat_context(selected, project_id, scope, task_id=job.job_id,
                                      session_id=job.session_id, instruction=job.instruction)
    except ValueError as error:
        if not str(error).startswith("required_combat_context_budget_exceeded"):
            raise
        # 普通分析仍可进行；显式或自主委派消费同一冻结失败，不能临时换新材料。
        return {"error": str(error)}
    return json.loads(json.dumps(asdict(frozen), ensure_ascii=False))


def consult_combat(runtime, job, *, main_step):
    current = runtime.get(job.job_id)
    if current.combat_results:
        raise ValueError("combat_delegation_limit")
    raw = deepcopy(job.combat_context)
    if raw is None:
        raise ValueError("combat_context_unavailable")
    if "error" in raw:
        raise ValueError(raw["error"])
    raw["scope"] = CombatScope(tuple(raw["scope"]["chapter_numbers"]), raw["scope"]["purpose"])
    raw["sources"] = tuple(raw["sources"])
    request = CombatRequest(**raw)

    def execute(messages, *, step, sources):
        capture = ContextCapture()
        # 正文在完整消息中原样捕获；引用登记准确区分已读与仅目录。
        for source in request.sources:
            capture.add("战斗冻结来源", source["source_ref"], reason="read" if source["source_id"] in sources else "catalog_only",
                        evidence_ref=source["source_id"], hash=source.get("hash"), version=source.get("version"),
                        usage="recorded" if source["source_id"] in sources else "not_in_model")
        return runtime._execute_story_step(job, messages, capture, f"combat:{main_step}:{step}")

    result = run_combat_expert(request, execute_step=execute, read_source=read_combat_source)
    # 重试只复用原输入身份；结果属于这次任务，不能冒充原失败任务结果。
    value = {**asdict(result), "job_id": job.job_id}
    runtime._set(job.job_id, combat_results=(*current.combat_results, value))
    return value


def run_chapter_turn(runtime, job, messages, capture):
    frozen = job.main_input
    if frozen:
        messages = [ModelMessage(item["role"], item["content"]) for item in frozen]
        # 重试的段偏移也来自首次装配，不能与最新上下文混用。
        capture.entries = deepcopy((job.analysis_state or {}).get("capture_entries", []))
    else:
        messages = list(messages)
        messages[0] = ModelMessage("system", messages[0].content + "\n" + PROTOCOL)
        if sum(len(item.content) for item in messages) > MAX_INPUT_CHARS:
            raise ValueError("required_story_context_budget_exceeded")
        runtime._set(job.job_id, main_input=tuple(asdict(item) for item in messages))
    trace = []
    # 正文写作先由主 Agent 判断是否需要专家；显式入口仍然直接委派。
    if job.requested_expert == "combat":
        value = consult_combat(runtime, job, main_step=0)
        trace.append({"step": 0, "input": {"action": "consult_combat"}, "result": value, "selection": "explicit"})
        messages.append(ModelMessage("user", "专家工具结果：" + json.dumps(value, ensure_ascii=False)))
        capture = ContextCapture()
        runtime._set(job.job_id, tool_trace=tuple(trace))
    for step in range(1, MAX_STEPS + 1):
        if sum(len(item.content) for item in messages) > MAX_INPUT_CHARS:
            return "本轮输入预算已用完，剩余问题未知，请缩小范围。"
        raw = runtime._execute_story_step(job, messages, capture, step)
        try:
            action = json.loads(raw)
        except (TypeError, ValueError):
            # 兼容已有直接分析文本；貌似工具 JSON 的错误不能降级成成功。
            if str(raw).lstrip().startswith(("{", "[")):
                raise ValueError("chapter_model_json_invalid")
            action = {"action": "finish", "reply": raw}
        if not isinstance(action, dict):
            raise ValueError("chapter_tool_not_allowed")
        if action.get("action") == "finish" and set(action) == {"action", "reply"}:
            if not isinstance(action["reply"], str) or not action["reply"].strip():
                raise ValueError("chapter_reply_invalid")
            trace.append({"step": step, "input": action, "result": "finished"})
            runtime._set(job.job_id, tool_trace=tuple(trace))
            return action["reply"]
        if action != {"action": "consult_combat"}:
            raise ValueError("chapter_tool_not_allowed")
        value = consult_combat(runtime, job, main_step=step)
        trace.append({"step": step, "input": action, "result": value})
        runtime._set(job.job_id, tool_trace=tuple(trace))
        messages.extend([ModelMessage("assistant", raw), ModelMessage("user", "专家工具结果：" + json.dumps(value, ensure_ascii=False))])
        capture = ContextCapture()
    return "本轮工具步骤预算已用完；未完成的判断仍未知，请缩小范围或继续讨论。"


def freeze_analysis_state(job, context, formal_word_count, capture):
    decision = {"decision_id": job.decision_id or context.decision.decision_id, "intent": job.instruction,
                "target_chapter": job.chapter_number, "context_refs": list(context.source_refs),
                "created_at": context.decision.created_at, "target_words": job.target_words,
                "tolerance_words": job.tolerance_words, "min_words": job.min_words, "max_words": job.max_words,
                "formal_word_count": formal_word_count, "project_id": job.project_id,
                "session_id": job.session_id, "task_id": job.job_id}
    return {"decision": decision, "capture_entries": deepcopy(capture.entries)}


def replay_chapter_analysis(runtime, job):
    """已送达模型的分析重试直接回放旧装配，不再触碰最新正文、草稿或经验。"""
    content = run_chapter_turn(runtime, job, (), ContextCapture())
    decision = {**deepcopy(job.analysis_state["decision"]), "task_id": job.job_id, "analysis": str(content)}
    runtime._write_decision(decision["decision_id"], decision)
    runtime._set(job.job_id, status="completed", message="分析已完成，正文未修改。",
                 decision_id=decision["decision_id"], reply=content)
