"""章节受理时冻结正式故事设定，后续模型组装只消费该快照。"""

import json
from copy import deepcopy
from pathlib import Path

from creative_os.story_architecture_store import StoryArchitectureStore, render_story
from creative_os.combat_context_selection import select_confirmed_combat


MAX_STORY_CONTEXT_CHARS = 48000


def chapter_story_context(confirmed, chapter_number):
    """完整证据留在快照，只将普通设定与本章计划编译为模型输入。"""
    content = confirmed.get("content")
    if content is None:
        # 旧任务只有纯故事文本，不能用最新候选补写它的历史证据。
        ordinary, plans = confirmed["text"], ()
    else:
        keys = {plan["block_key"] for plan in content.get("combat_plans", [])}
        ordinary = render_story({"blocks": [block for block in content["blocks"] if block["key"] not in keys],
                                 "open_questions": content["open_questions"]})
        plans = select_confirmed_combat(confirmed, chapter_number)
    if len(ordinary) + sum(len(plan["text"]) for plan in plans) > MAX_STORY_CONTEXT_CHARS:
        raise ValueError("required_story_context_budget_exceeded")
    return ordinary, plans


def freeze_confirmed_story(root, project_id, *, required=False, chapter_number=None, require_confirmed_combat=False):
    root = Path(root)
    metadata = root / "project.json"
    story_mode = json.loads(metadata.read_text(encoding="utf-8")).get("story_mode", False) if metadata.exists() else False
    view = StoryArchitectureStore(root, project_id).view()
    confirmed = view["confirmed"]
    if confirmed is None:
        if required or story_mode or require_confirmed_combat:
            raise ValueError("story_confirmation_required")
        return None
    frozen = {**deepcopy(confirmed), "project_id": project_id,
              "source_ref": f"story-confirmed:{project_id}:{confirmed['version']}:{confirmed['hash']}"}
    if chapter_number is not None:
        _, plans = chapter_story_context(frozen, chapter_number)
        if require_confirmed_combat and not plans:
            raise ValueError("combat_plan_confirmation_required")
    elif len(confirmed["text"]) > MAX_STORY_CONTEXT_CHARS:
        raise ValueError("required_story_context_budget_exceeded")
    return frozen
