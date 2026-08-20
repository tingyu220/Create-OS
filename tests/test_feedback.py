import json

import pytest

from creative_os.memory.approval import approve_candidate
from creative_os.memory.feedback import (
    FeedbackOutcome,
    FeedbackStore,
    FeedbackValidationError,
    create_lesson_candidate,
    record_feedback,
)
from creative_os.memory.model import MemoryStatus
from creative_os.memory.retriever import MemoryQuery, MemoryRetriever
from creative_os.memory.store import JsonMemoryStore


def test_feedback_is_append_only_and_non_accepted_requires_reason(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(FeedbackValidationError):
        FeedbackStore(project)
        from creative_os.memory.feedback import FeedbackRecord

        FeedbackRecord.new(project_id="project", task_id="task", result_ref="result", outcome=FeedbackOutcome.REVISED)

    from creative_os.memory.feedback import FeedbackRecord

    feedback = FeedbackRecord.new(
        project_id="project", task_id="task", result_ref="chapter-001", outcome=FeedbackOutcome.REVISED,
        reason="主角的选择没有代价", chapter_number=1, character_names=["林川"], revision_ref="revision-1",
    )
    record_feedback(project, feedback)
    assert FeedbackStore(project).list() == [feedback]
    event_lines = (project / ".creative_os" / "runtime" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert json.loads(event_lines[-1])["event_type"] == "UserRevised"


def test_lesson_stays_candidate_until_human_approval_then_retriever_finds_it(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    from creative_os.memory.feedback import FeedbackRecord

    feedback = FeedbackRecord.new(
        project_id="project", task_id="task", result_ref="chapter-002", outcome=FeedbackOutcome.REGENERATED,
        reason="人物不能在没有铺垫时突然改变立场", chapter_number=2, character_names=["林川"],
    )
    item = create_lesson_candidate(
        project, feedback, title="保持人物主动性", content="林川面对威胁会先观察、试探或谈判，不会无理由服从。", character_name="林川",
    )
    assert item.status == MemoryStatus.CANDIDATE
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    approve_candidate(store, item.id, actor="tingyu", note="确认可复用")
    result = MemoryRetriever().retrieve(
        MemoryQuery(task_id="next", project_id="project", user_id="tingyu", domain="novel", task_kind="writing", tags={"character:林川"}),
        [store],
    )
    assert [found.id for found in result.items] == [item.id]
    assert json.loads(result.items[0].content)["kind"] == "character_lesson"


def test_project_lesson_does_not_require_character_tag(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    from creative_os.memory.feedback import FeedbackRecord

    feedback = FeedbackRecord.new(project_id="project", task_id="task", result_ref="chapter-003", outcome=FeedbackOutcome.REJECTED, reason="场景之间直接拼接，缺少过渡", chapter_number=3)
    item = create_lesson_candidate(project, feedback, title="场景转场", content="连续场景之间必须有明确的空间、动作或情绪过渡。")
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    approve_candidate(store, item.id, actor="tingyu", note="确认")
    result = MemoryRetriever().retrieve(
        MemoryQuery(task_id="next", project_id="project", user_id="tingyu", domain="novel", task_kind="writing", tags={"transition"}),
        [store],
    )
    assert result.items[0].id == item.id


def test_unapproved_lesson_is_not_retrieved(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    from creative_os.memory.feedback import FeedbackRecord

    feedback = FeedbackRecord.new(project_id="project", task_id="task", result_ref="chapter-004", outcome=FeedbackOutcome.REJECTED, reason="重复使用相同的场景功能", chapter_number=4)
    item = create_lesson_candidate(project, feedback, title="场景功能要变化", content="连续章节不能只重复同一种推进方式。")
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    result = MemoryRetriever().retrieve(
        MemoryQuery(task_id="next", project_id="project", user_id="tingyu", domain="novel", task_kind="writing", tags={"novel", "lesson"}),
        [store],
    )
    assert result.items == []
    assert store.get(item.id).status == MemoryStatus.CANDIDATE
