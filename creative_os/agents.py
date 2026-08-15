from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AgentContractError(ValueError):
    pass


class AgentRole(StrEnum):
    DIRECTOR = "director"
    PLANNER = "planner"
    ARCHITECT = "architect"
    WRITER = "writer"
    REVIEWER = "reviewer"
    COMPILER = "compiler"


@dataclass(frozen=True, slots=True)
class AgentContract:
    role: AgentRole
    responsibility: str
    inputs: list[str]
    outputs: list[str]
    permissions: list[str]
    forbidden: list[str]
    error_handling: list[str]
    acceptance_criteria: list[str]

    def validate(self) -> None:
        required_lists = {
            "inputs": self.inputs,
            "outputs": self.outputs,
            "permissions": self.permissions,
            "forbidden": self.forbidden,
            "error_handling": self.error_handling,
            "acceptance_criteria": self.acceptance_criteria,
        }
        empty = [name for name, value in required_lists.items() if not value]
        if empty:
            raise AgentContractError(f"Agent contract has empty sections: {', '.join(empty)}")
        if "万能" in self.responsibility or "all" in self.responsibility.lower():
            raise AgentContractError(f"Agent responsibility is too broad: {self.role}")


def default_novel_agent_contracts() -> dict[AgentRole, AgentContract]:
    contracts = {
        AgentRole.DIRECTOR: AgentContract(
            role=AgentRole.DIRECTOR,
            responsibility="维护小说定位、项目级约束和重大创作决策",
            inputs=["Project Brief", "Project State", "用户要求", "当前阶段"],
            outputs=["Direction Decision", "Creative Constraints", "Priority"],
            permissions=["读取项目级状态", "提出方向性决策"],
            forbidden=["直接写章节正文", "直接修改 Knowledge", "跳过 Workflow"],
            error_handling=["定位缺失时返回阻塞", "重大冲突时生成决策请求"],
            acceptance_criteria=["方向决策可追溯", "不改变已冻结核心设定"],
        ),
        AgentRole.PLANNER: AgentContract(
            role=AgentRole.PLANNER,
            responsibility="拆解项目目标、生成任务和维护任务依赖",
            inputs=["Project State", "Workflow", "Domain Rules", "Current Issues"],
            outputs=["Task", "Task Dependency", "Acceptance Criteria", "Next Step"],
            permissions=["创建任务草案", "标记阻塞原因"],
            forbidden=["直接生成最终正文", "直接读取整个 Vault", "绕过 Task Engine"],
            error_handling=["依赖缺失时阻塞任务", "重复任务时复用原任务"],
            acceptance_criteria=["任务有明确验收标准", "下一步唯一且可执行"],
        ),
        AgentRole.ARCHITECT: AgentContract(
            role=AgentRole.ARCHITECT,
            responsibility="构建世界观、人物、关系、剧情结构和时间线",
            inputs=["Task", "Project Brief", "Retrieved Knowledge", "Novel Schema"],
            outputs=["Character", "World Rule", "Plot Structure", "Timeline Event", "Relationship"],
            permissions=["生成结构性知识候选", "补充非核心设定细节"],
            forbidden=["无记录修改核心设定", "直接写入 Knowledge"],
            error_handling=["设定冲突时输出 Conflict", "证据不足时标记 Uncertainty"],
            acceptance_criteria=["结构产物符合 Novel Schema", "核心冲突和人物动机明确"],
        ),
        AgentRole.WRITER: AgentContract(
            role=AgentRole.WRITER,
            responsibility="根据 Scene Task 和 Context 生成正文草稿",
            inputs=["Scene Task", "Scene Context", "Character Context", "World Context", "Previous Scene Summary", "Style Guide"],
            outputs=["Draft", "New Fact Candidates", "New Event Candidates", "Uncertainty"],
            permissions=["生成 Scene Draft", "提出新增事实候选"],
            forbidden=["自行改变核心设定", "自行创建重大剧情转折", "直接读写 Knowledge"],
            error_handling=["Context 不足时返回 Uncertainty", "目标冲突时不生成正文"],
            acceptance_criteria=["完成 Scene Goal", "不违反人物和世界规则", "风格约束可检查"],
        ),
        AgentRole.REVIEWER: AgentContract(
            role=AgentRole.REVIEWER,
            responsibility="检查剧情、人物、世界观、时间线和章节目标",
            inputs=["Draft", "Task Acceptance Criteria", "Relevant Knowledge", "Review Rules"],
            outputs=["Issue", "Severity", "Evidence", "Repair Task", "Pass / Fail"],
            permissions=["判定通过或失败", "生成修复任务"],
            forbidden=["直接重写正文", "无证据判错"],
            error_handling=["无法判断时标记人工复核", "高严重度问题阻断进入 Compiler"],
            acceptance_criteria=["Issue 有证据", "Repair Task 可执行", "误报可追踪"],
        ),
        AgentRole.COMPILER: AgentContract(
            role=AgentRole.COMPILER,
            responsibility="从通过 Review 的结果抽取结构化知识更新建议",
            inputs=["Approved Result", "Review Result", "Existing Knowledge"],
            outputs=["Knowledge Patch", "Summary", "State Update Proposal", "Index Update"],
            permissions=["生成 Knowledge Patch", "生成状态更新建议"],
            forbidden=["无条件写入 Knowledge", "覆盖旧设定", "跳过冲突检测"],
            error_handling=["结构校验失败时拒绝写入", "冲突时生成 Conflict"],
            acceptance_criteria=["抽取结果可校验", "更新来源可追溯", "不产生重复 Fact"],
        ),
    }
    validate_agent_contracts(contracts)
    return contracts


def validate_agent_contracts(contracts: dict[AgentRole, AgentContract]) -> None:
    missing = set(AgentRole) - set(contracts)
    if missing:
        raise AgentContractError(f"Missing agent contracts: {', '.join(sorted(role.value for role in missing))}")
    for contract in contracts.values():
        contract.validate()
