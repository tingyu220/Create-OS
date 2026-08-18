import json

import pytest

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
)
from creative_os.domains.narrative_memory import save_narrative_candidate
from creative_os.domains.novel_continuation import ContinuationBlockedError, build_next_chapter
from creative_os.novel_continuation_runner import continue_one_chapter, promote_passing_draft
from creative_os.memory.approval import approve_candidate
from creative_os.memory.model import MemoryEvidence
from creative_os.memory.store import JsonMemoryStore


def _project(tmp_path):
    project = tmp_path / "文明升阶"
    (project / "production/final_chapters").mkdir(parents=True)
    (project / ".creative_os/import").mkdir(parents=True)
    (project / "production/final_chapters/chapter_001.md").write_text("# 第1章\n上一章结尾。", encoding="utf-8")
    (project / ".creative_os/import/baseline.json").write_text(
        json.dumps({"world_rules": [], "characters": [], "plot_milestones": [], "hooks": [], "style_constraints": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (project / ".creative_os/import/conflicts.json").write_text("[]", encoding="utf-8")
    (project / ".creative_os/import/approval.json").write_text('{"resolutions": {}}', encoding="utf-8")
    return project


def _approved_contract(project, *, chapter: int = 2):
    decision = NarrativeDecision(
        chapter=chapter,
        profile_id="civilization-profile",
        volume_id="volume-1",
        arc_id="arc-identity",
        arc_phase=ArcPhase.ESCALATION,
        arc_goal="调查异常信息来源",
        inherited_pressure="主角刚收到警告",
        future_pressures=("权限审查",),
        chapter_contract=ChapterContract(
            functions=("推进主线",),
            dramatic_question="林子轩是否相信警告？",
            protagonist_choice=ProtagonistChoice("林子轩", "保留证据", ("立刻上报",), "暴露自己", "被列入观察名单"),
            reader_change=ReaderChange("读者怀疑警告来源", "读者确认信息遭到篡改"),
            information=InformationPlan(("日志被修改",), ("发送者身份",), ()),
            pressure_curve=PressureCurve("警觉", "试探", "被盯上"),
            foreshadow_actions=("加深内部泄露线索",),
            ending_shift="主角发现自己被监控",
            target_chinese_chars=2000,
            forbidden=("周远就是发送者",),
        ),
    )
    item = save_narrative_candidate(
        project,
        decision,
        evidence=[MemoryEvidence(source_type="test", source_id=f"contract-{chapter:03d}")],
    )
    approve_candidate(JsonMemoryStore(project / ".creative_os" / "memory"), item.id, actor="tester", note="批准")
    return decision


def test_required_narrative_contract_blocks_real_continuation_when_missing(tmp_path):
    with pytest.raises(ContinuationBlockedError, match="narrative decision"):
        build_next_chapter(_project(tmp_path), require_narrative_contract=True)


def test_runner_can_require_narrative_contract_before_model_call(tmp_path):
    with pytest.raises(ContinuationBlockedError, match="narrative decision"):
        continue_one_chapter(_project(tmp_path), client=None, require_narrative_contract=True)


def test_draft_promotion_can_require_narrative_contract(tmp_path):
    project = _project(tmp_path)
    draft = project / ".creative_os/llm_writer/drafts/chapter_002.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# 第2章\n" + "正文" * 3000, encoding="utf-8")

    with pytest.raises(ContinuationBlockedError, match="narrative decision"):
        promote_passing_draft(project, require_narrative_contract=True)


def test_approved_narrative_contract_blocks_forbidden_information_in_draft(tmp_path):
    project = _project(tmp_path)
    _approved_contract(project)
    text = "# 第2章\n" + "正文" * 1600 + "周远就是发送者。"

    result = continue_one_chapter(project, client=type("Client", (), {"complete": lambda self, *_args, **_kwargs: text})())

    assert result.status == "fail"
    assert "narrative:forbidden_information_revealed" in result.issues
    assert not (project / "production/final_chapters/chapter_002.md").exists()
    review = json.loads((project / ".creative_os/reviews/chapter_002_continuation.json").read_text(encoding="utf-8"))
    assert review["narrative_issues"] == [
        {
            "code": "forbidden_information_revealed",
            "severity": "high",
            "evidence": "周远就是发送者",
        }
    ]


def test_approved_contract_controls_length_and_writer_instructions(tmp_path):
    project = _project(tmp_path)
    _approved_contract(project)
    task, context = build_next_chapter(project)

    assert task.target_chinese_chars == 2000
    assert task.min_chinese_chars == 1500
    assert "周远就是发送者" in task.forbidden_contradictions
    assert context.contains_source("narrative:chapter:002")

    class CaptureClient:
        messages = []

        def complete(self, messages, **_kwargs):
            self.messages = messages
            return "# 第2章\n" + "正文" * 1600

    client = CaptureClient()
    result = continue_one_chapter(project, client=client)

    assert result.status == "pass"
    prompt = client.messages[-1].content
    assert "章节叙事合同" in prompt
    assert "人物主动选择：林子轩应保留证据" in prompt
    assert "周远就是发送者" in prompt
    assert "目标中文字符数：约 2000" in prompt


def test_reviewer_loads_recent_contracts_before_promoting_next_chapter(tmp_path):
    project = _project(tmp_path)
    (project / "production/final_chapters/chapter_002.md").write_text("# 第2章\n上一章结尾。", encoding="utf-8")
    _approved_contract(project, chapter=2)
    _approved_contract(project, chapter=3)

    result = continue_one_chapter(project, client=type("Client", (), {"complete": lambda self, *_args, **_kwargs: "# 第3章\n" + "正文" * 1600})())

    assert result.status == "fail"
    assert "narrative:duplicate_recent_function" in result.issues
    assert not (project / "production/final_chapters/chapter_003.md").exists()
