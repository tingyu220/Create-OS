"""从不可变确认版本选择章节计划；没有文件读取或候选回填。"""

from copy import deepcopy

from creative_os.combat_story_candidate import validate_combat_plans
from creative_os.story_architecture_store import render_story


def select_confirmed_combat(confirmed, chapter_number) -> tuple[dict, ...]:
    """空章节集合只表示全书研究；返回内容和来源均是冻结版本的独立副本。"""
    if type(chapter_number) is not int or chapter_number <= 0:
        raise ValueError("chapter_scope_invalid")
    if confirmed is None or "content" not in confirmed:
        return ()
    content = confirmed["content"]
    plans = validate_combat_plans(content.get("combat_plans", []), content["blocks"], confirmed.get("project_id"))
    blocks = {block["key"]: block for block in content["blocks"]}
    selected = []
    for plan in plans:
        if chapter_number not in plan["scope"]["chapter_numbers"]:
            continue
        ref = confirmed.get("source_ref") or f"story-confirmed:{plan['project_id']}:{confirmed['version']}:{confirmed['hash']}"
        block = deepcopy(blocks[plan["block_key"]])
        selected.append({**plan, "block": block,
            "text": render_story({"blocks": [block], "open_questions": [], "combat_plans": [plan]}),
            "version": confirmed["version"], "hash": confirmed["hash"],
            "source_ref": ref + "#" + plan["block_key"]})
    return tuple(selected)
