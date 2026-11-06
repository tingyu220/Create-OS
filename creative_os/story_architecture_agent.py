"""前期讨论的有界工具循环；复用同一任务队列与单步模型执行入口。"""

import json
from dataclasses import asdict

from creative_os.llm_writer import ModelMessage
from creative_os.writer_context_sources import ContextCapture
from creative_os.chapter_agent_tools import consult_combat, PROTOCOL as EXPERT_PROTOCOL


MAX_STEPS = 6
MAX_INPUT_CHARS = 100000
PROTOCOL = """你是小说前期架构讨论 Agent。根据作者 Idea 和对话自行选择最有价值的讨论顺序，提出问题、备选或修订，不按固定问卷推进。
故事核心、世界、人物、冲突、整体方向是可扩展内容块；未知事项放入 open_questions，不编造已经获作者认可的事实。
候选仅是建议；正式设定以 confirmed 为准。聊天中的“可以”不等于确认。你无权确认、发布或写章节正文。
每次只输出一个 JSON 对象，不使用 Markdown 代码围栏。合法 action 与唯一字段如下：
{"action":"read_candidate"}
{"action":"read_confirmed"}
{"action":"propose_revision","expected_revision":0,"blocks":[{"key":"自定稳定键","title":"内容标题","text":"完整内容"}],"open_questions":["未定问题"]}
propose_revision 是完整新候选，不是局部 patch；保留仍适用内容。expected_revision 必须匹配当前候选。
{"action":"consult_combat"}
{"action":"finish","reply":"给作者的自然语言说明、问题或备选"}
{"action":"finish_turn","reply":"给作者的自然语言说明、问题或备选"}
可连续调用多个工具，每步一个 JSON；需要作者补充时 finish_turn。不得输出 confirm/publish 等其它动作。"""


def decode_action(text):
    try:
        action = json.loads(text)
    except (TypeError, ValueError) as error:
        raise ValueError("story_model_json_invalid") from error
    fields = {"read_candidate": {"action"}, "read_confirmed": {"action"},
              "propose_revision": {"action", "expected_revision", "blocks", "open_questions"},
              "finish_turn": {"action", "reply"}, "finish": {"action", "reply"}, "consult_combat": {"action"}}
    if not isinstance(action, dict) or not isinstance(action.get("action"), str) or action["action"] not in fields or set(action) != fields[action["action"]]:
        raise ValueError("story_tool_not_allowed")
    if action["action"] in {"finish_turn", "finish"} and (not isinstance(action["reply"], str) or not action["reply"].strip()):
        raise ValueError("story_reply_invalid")
    return action


def run_story_turn(runtime, job):
    runtime._set(job.job_id, status="thinking", message="正在结合 Idea、讨论历史和当前设定思考。")
    history = runtime.conversations.conversation(None)["messages"]
    # 历史含本轮原文；失败重试不会另造作者消息。
    if job.main_input:
        frozen = [ModelMessage(item["role"], item["content"]) for item in job.main_input]
        messages, state_message = frozen[:-1], frozen[-1]
        state = state_message.content.removeprefix("本步领域状态（候选不是正式事实）：\n")
    else:
        messages = [ModelMessage("system", PROTOCOL + "\n" + EXPERT_PROTOCOL)] + [ModelMessage(item["role"], item["content"]) for item in history]
        view = runtime.story.view()
        state = json.dumps({"project_id": runtime.project_id, "session_id": job.session_id, "candidate": view["candidate"], "confirmed": view["confirmed"]}, ensure_ascii=False)
        state_message = ModelMessage("user", "本步领域状态（候选不是正式事实）：\n" + state)
        runtime._set(job.job_id, main_input=tuple(asdict(item) for item in [*messages, state_message]))
    trace = []
    frozen_state = json.loads(state)
    if job.requested_expert == "combat":
        value = consult_combat(runtime, job, main_step=0)
        trace.append({"step": 0, "input": {"action": "consult_combat"}, "result": value, "selection": "explicit"})
        messages.append(ModelMessage("user", "专家工具结果：" + json.dumps(value, ensure_ascii=False)))
        runtime._set(job.job_id, tool_trace=tuple(trace))
    for step in range(1, MAX_STEPS + 1):
        step_messages = [*messages, state_message]
        if sum(len(message.content) for message in step_messages) > MAX_INPUT_CHARS:
            raise ValueError("story_input_budget_exceeded_continue_with_shorter_context")
        capture = ContextCapture()
        capture.add("本步故事候选与正式设定", f"story-state:{runtime.project_id}:{step}", state, version=step, message_start=len("本步领域状态（候选不是正式事实）：\n"))
        raw = runtime._execute_story_step(job, step_messages, capture, step)
        action = decode_action(raw)
        name = action["action"]
        if name in {"finish_turn", "finish"}:
            trace.append({"step": step, "input": action, "result": "finished"})
            runtime._set(job.job_id, status="completed", message="本轮讨论已完成，候选可编辑；正式设定须作者明确确认。", tool_trace=tuple(trace), reply=action["reply"])
            return
        if name == "consult_combat":
            result = consult_combat(runtime, job, main_step=step)
        elif name == "read_candidate":
            result = frozen_state["candidate"]
        elif name == "read_confirmed":
            result = frozen_state["confirmed"]
        else:
            result = runtime.story.propose(job.session_id, action["blocks"], action["open_questions"],
                                           expected_revision=action["expected_revision"], actor="agent",
                                           operation_id=f"agent:{job.job_id}:step:{step}")
            frozen_state["candidate"] = result
            state = json.dumps(frozen_state, ensure_ascii=False)
            state_message = ModelMessage("user", "本步领域状态（候选不是正式事实）：\n" + state)
        trace.append({"step": step, "input": action, "result": result})
        runtime._set(job.job_id, tool_trace=tuple(trace), message=f"已执行 {name}，继续判断下一步。")
        messages.extend([ModelMessage("assistant", raw), ModelMessage("user", "工具结果：" + json.dumps(result, ensure_ascii=False))])
    runtime._set(job.job_id, status="completed", message="本轮工具步数已用完，可继续讨论；已有候选已保留。", tool_trace=tuple(trace),
                 reply="本轮已达到工具步数预算。已保留讨论记录和有效候选，请补充想法或发送“继续讨论”。")
