import json
from dataclasses import replace

import pytest

from creative_os.domains.narrative_decision import (
    ArcPhase,
    ChapterContract,
    InformationPlan,
    NarrativeDecision,
    PressureCurve,
    ProtagonistChoice,
    ReaderChange,
    SceneContract,
    ScenePlan,
    TechnologyContract,
    TechnologyPlan,
)
from creative_os.domains.narrative_memory import save_narrative_candidate
from creative_os.domains.novel_continuation import ContinuationBlockedError, build_next_chapter
from creative_os.domains.writer_admission import AdmittedContractProjection
from creative_os.novel_continuation_runner import _messages, continue_one_chapter, promote_passing_draft
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
    with pytest.raises(TypeError, match="PreparedWriterRun"):
        continue_one_chapter(_project(tmp_path), client=None)


def test_draft_promotion_can_require_narrative_contract(tmp_path):
    project = _project(tmp_path)
    draft = project / ".creative_os/llm_writer/drafts/chapter_002.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# 第2章\n" + "正文" * 3000, encoding="utf-8")

    with pytest.raises(TypeError, match="PreparedWriterRun"):
        promote_passing_draft(project)


def test_legacy_approved_contract_cannot_enter_public_writer_exit(tmp_path):
    project = _project(tmp_path)
    _approved_contract(project)
    text = "# 第2章\n" + "正文" * 1600 + "周远就是发送者。"

    with pytest.raises(TypeError, match="PreparedWriterRun"):
        continue_one_chapter(project, client=type("Client", (), {"complete": lambda self, *_args, **_kwargs: text})())
    assert not (project / "production/final_chapters/chapter_002.md").exists()


def test_legacy_approved_contract_is_not_loaded_into_context(tmp_path):
    project = _project(tmp_path)
    _approved_contract(project)
    task, context = build_next_chapter(project)

    assert task.contract_projection is None
    assert not context.contains_source("narrative:chapter:002")


def test_legacy_contracts_cannot_bypass_prepared_run_for_next_chapter(tmp_path):
    project = _project(tmp_path)
    (project / "production/final_chapters/chapter_002.md").write_text("# 第2章\n上一章结尾。", encoding="utf-8")
    _approved_contract(project, chapter=2)
    _approved_contract(project, chapter=3)

    with pytest.raises(TypeError, match="PreparedWriterRun"):
        continue_one_chapter(project, client=type("Client", (), {"complete": lambda self, *_args, **_kwargs: "# 第3章\n" + "正文" * 1600})())
    assert not (project / "production/final_chapters/chapter_003.md").exists()


def test_writer_prompt_contains_approved_scene_and_technology_contract(tmp_path):
    project = _project(tmp_path)
    _approved_contract(project)
    store = JsonMemoryStore(project / ".creative_os" / "memory")
    item = store.get("narrative-chapter-002")
    payload = json.loads(item.content)
    payload["schema_version"] = 2
    payload["chapter_contract"]["scene_plan"] = {
        "scenes": [{"id":"s1","order":1,"place_id":"gobi","place_label":"西北试验场","place_class":"field","interior_exterior":"exterior","time_window":"深夜","participants":["林子轩","工人"],"viewpoint":"林子轩","ordinary_people_present":True,"goal":"查故障","conflict":"工期冲突","action":"现场停机","information_change":"旧图缺失","state_change":"试验暂停","entry_reason":"远程数据不足","exit_trigger":"复盘完成","inherited_from_previous":False}],
        "chapter_spatial_intent":"现场行动","required_world_slice":"工程劳动者","allowed_same_place_run":2,"exception_reason":""
    }
    payload["chapter_contract"]["technology_plan"] = {"technologies":[{"id":"fusion","name":"偏滤器","role":"supporting","birth_reason":"解决热流烧蚀","source":"人类工程化","prerequisites":["耐热材料"],"validation_stage":"现场试验","first_application":"试验堆","social_diffusion":["工业热交换"],"cost":"延期","changed_domains":["ordinary_life"]}]}
    store.replace(replace(item, content=json.dumps(payload, ensure_ascii=False)))

    task, context = build_next_chapter(project)
    canonical = NarrativeDecision.from_json(json.dumps(payload, ensure_ascii=False)).to_json()
    task = replace(
        task,
        contract_projection=AdmittedContractProjection(
            "narrative-chapter-002", 1, "a" * 64, canonical,
        ),
    )
    prompt = _messages(task, context)[-1].content

    assert "场景结构合同" in prompt and "西北试验场" in prompt
    assert "技术发展合同" in prompt and "偏滤器" in prompt
