"""Agent 自然语言意图入口契约；本阶段只受理，不执行自动改稿。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class AgentIntentRequest:
    project_id: str
    chapter_number: int
    instruction: str
    actor: str


@dataclass(frozen=True, slots=True)
class AgentIntentReceipt:
    intent_id: str
    status: str
    message: str
    instruction: str


def accept_agent_intent(request: AgentIntentRequest) -> AgentIntentReceipt:
    if not request.instruction.strip():
        raise ValueError("instruction_required")
    if request.chapter_number <= 0:
        raise ValueError("chapter_number_invalid")
    return AgentIntentReceipt(uuid4().hex, "accepted", "已受理，Agent 将自行选择必要上下文进行检查。", request.instruction.strip())

