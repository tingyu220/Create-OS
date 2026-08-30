from __future__ import annotations

from creative_os.domains.narrative_decision import ChapterContract, NullablePlan, SceneContract
from creative_os.domains.novel_writer import NovelWritingRequest
from creative_os.runtime import ModelMessage


DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION = (
    "你是小说正文 Writer。严格依据已批准合同写作；只输出可发布正文；"
    "不得输出分析、提纲、代码块或系统术语；不得把未授权信息写成既成事实。"
)


def build_novel_writer_messages(
    request: NovelWritingRequest,
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
) -> list[ModelMessage]:
    request.chapter_contract.scene_plan.validate(required=True, novel_required=True)
    sections = _contract_sections(request)
    return [ModelMessage("system", system_instruction.strip()), ModelMessage("user", "\n\n".join(sections))]


def _contract_sections(request: NovelWritingRequest) -> list[str]:
    contract = request.chapter_contract
    choice = contract.protagonist_choice
    reader = contract.reader_change
    info = contract.information
    return [
        f"章节身份：{request.chapter_id}（合同章节：{contract.chapter_id}）",
        f"章节功能：{'；'.join(contract.functions)}",
        f"戏剧问题：{contract.dramatic_question}",
        (
            "主人公选择："
            f"行动者={choice.actor or '未指定'}；行动={choice.action or '未指定'}；"
            f"替代方案={'；'.join(choice.alternatives) or '无'}；代价={choice.cost or '未指定'}；"
            f"后果={choice.consequence or '未指定'}"
        ),
        f"读者变化：从{reader.before}到{reader.after}",
        f"目标字数：{contract.target_chinese_chars}",
        _scene_section(contract),
        (
            "伏笔："
            f"{'；'.join(_plan_values(contract.foreshadow_actions)) or _plan_reason(contract.foreshadow_actions)}"
        ),
        f"禁止项：{'；'.join(_plan_values(contract.forbidden)) or _plan_reason(contract.forbidden)}",
        f"补充指令：{request.instruction.strip() or '无'}",
    ]


def _scene_section(contract: ChapterContract) -> str:
    scene_plan = contract.scene_plan
    lines = [
        "场景：",
        f"空间意图：{scene_plan.chapter_spatial_intent}",
        f"外部世界/社会切面：{scene_plan.required_world_slice or '本章无强制项'}",
    ]
    for scene in scene_plan.scenes:
        lines.append(_scene_line(scene))
    return "\n".join(lines)


def _scene_line(scene: SceneContract) -> str:
    closure = scene.closure
    return (
        f"{scene.order}. {scene.place_label}（{scene.place_id}，{scene.time_window}，{scene.interior_exterior}）；"
        f"目的：{scene.narrative_purpose}；目标：{scene.goal}；冲突：{scene.conflict}；行动：{scene.action}；"
        f"必要信息：{'；'.join(scene.essential_information)}；情绪变化：{scene.emotional_change}；"
        "闭合要求："
        f"目标={closure.goal_addressed}；冲突={closure.conflict_advanced}；"
        f"选择={closure.choice_made}；结果={closure.outcome_recorded}"
    )


def _plan_values(plan: NullablePlan) -> tuple[str, ...]:
    return plan.values


def _plan_reason(plan: NullablePlan) -> str:
    return plan.not_applicable_reason or "无"
