"""冻结证据上的只读专家循环；不持有 Runtime、文件路径或写入能力。"""

from copy import deepcopy
from dataclasses import asdict
import json
from uuid import uuid4

from creative_os.combat_model import CombatRequest, CombatResult
from creative_os.llm_writer import ModelMessage


MAX_STEPS = 4
MAX_READS = 8
MAX_SOURCE_CHARS = 12000
MAX_TOTAL_CHARS = 48000
MAX_INPUT_CHARS = 100000
PROTOCOL = """你是战斗编排专家。只研究本次冻结来源，提出自由文本的叙事建议，不把未来计划、未确认候选或邻章当作目标章事实。
按需选择读取顺序，可判断非战斗冲突更合适，或材料不足。目标正文缺失必须说明未知，不能推断章内缺陷。
只能输出一个 JSON 工具动作：
{"action":"read_source","source_id":"目录内引用"}
{"action":"finish","verdict":"combat/setup/noncombat/insufficient四选一","reply":"自然语言建议","alternatives":[],"foreshadowing":[],"evidence_refs":[],"unknowns":[]}
evidence_refs 只能引用实际读到正文的 source_id。所有数组元素是字符串；身份由服务器注入。
无权确认、发布、改稿、访问任意路径或再次委派；最多4步，尽早完成。"""


def source_catalog(request):
    """目录仅暴露冻结元数据，正文必须经 read_source 读取。"""
    return [{key: deepcopy(value) for key, value in source.items() if key != "text"} for source in request.sources]


def _decode(raw):
    try:
        action = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise ValueError("combat_model_json_invalid") from error
    fields = {"read_source": {"action", "source_id"}, "finish": {"action", "verdict", "reply", "alternatives", "foreshadowing", "evidence_refs", "unknowns"}}
    if (not isinstance(action, dict) or not isinstance(action.get("action"), str)
            or action["action"] not in fields or set(action) != fields[action["action"]]):
        raise ValueError("combat_tool_not_allowed")
    return action


def run_combat_expert(request, *, execute_step, read_source) -> CombatResult:
    if not isinstance(request, CombatRequest):
        raise ValueError("combat_request_invalid")
    # 回调得到的材料也与原请求隔离，不能就地更改嵌套冻结字段。
    request = deepcopy(request)
    header = {"instruction": request.instruction, "scope": asdict(request.scope), "sources": source_catalog(request)}
    messages = [ModelMessage("system", PROTOCOL), ModelMessage("user", json.dumps(header, ensure_ascii=False))]
    read_ids, reads, total = [], 0, 0

    def result(verdict, reply, alternatives=(), foreshadowing=(), evidence_refs=(), unknowns=()):
        return CombatResult(f"combat-result-{uuid4().hex}", request.project_id, request.job_id, verdict, reply,
                            tuple(alternatives), tuple(foreshadowing), tuple(evidence_refs), tuple(unknowns), request.scope)

    def exhausted(reason):
        return result("insufficient", "本轮专家预算已用完；未能完成的判断仍未知，请缩小范围。",
                      evidence_refs=read_ids, unknowns=(reason,))

    for step in range(1, MAX_STEPS + 1):
        if sum(len(item.content) for item in messages) > MAX_INPUT_CHARS:
            return exhausted("单步输入预算耗尽")
        raw = execute_step(tuple(messages), step=step, sources=tuple(read_ids))
        action = _decode(raw)
        if action["action"] == "finish":
            for key in ("alternatives", "foreshadowing", "evidence_refs", "unknowns"):
                if not isinstance(action[key], list) or any(not isinstance(item, str) for item in action[key]):
                    raise ValueError("combat_result_invalid")
            if not isinstance(action["reply"], str) or not action["reply"].strip():
                raise ValueError("combat_reply_invalid")
            if not set(action["evidence_refs"]) <= set(read_ids):
                raise ValueError("combat_evidence_not_read")
            return result(**{key: value for key, value in action.items() if key != "action"})
        source_id = action["source_id"]
        if not isinstance(source_id, str) or not any(item["source_id"] == source_id for item in request.sources):
            raise ValueError("combat_source_not_found")
        if reads >= MAX_READS:
            return exhausted("来源读取次数预算耗尽")
        source = read_source(deepcopy(request), source_id)
        reads += 1
        # 读取回调也不能扩大冻结权限或偷换正文。
        frozen = next(item for item in request.sources if item["source_id"] == source_id)
        if source != frozen:
            raise ValueError("combat_source_snapshot_mismatch")
        text = source.get("text", "")
        if len(text) > MAX_SOURCE_CHARS or total + len(text) > MAX_TOTAL_CHARS:
            return exhausted("来源字符预算耗尽")
        total += len(text)
        if source.get("usage") == "included" and source_id not in read_ids:
            read_ids.append(source_id)
        messages.extend([ModelMessage("assistant", raw), ModelMessage("user", "只读工具结果：" + json.dumps(source, ensure_ascii=False))])
    return exhausted("专家步骤预算耗尽")
