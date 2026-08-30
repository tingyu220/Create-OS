from dataclasses import replace

from creative_os.domains.novel_chapter_boundary import ChapterBoundary
from creative_os.domains.novel_review_model import (
    CharacterStateProposal,
    ConsistencyFinding,
    NovelReviewRequest,
)
from creative_os.domains.novel_reviewer import NovelReviewer
from tests.test_novel_scene_contract import _complete_scene
from tests.test_narrative_director import _v2_decision


def _request(**changes) -> NovelReviewRequest:
    decision = _v2_decision()
    scene_plan = replace(decision.chapter_contract.scene_plan, scenes=(_complete_scene(),))
    contract = replace(decision.chapter_contract, scene_plan=scene_plan)
    values = {
        "draft": "现场确认旧图缺失。\n\n林子轩承担停机代价，试验暂停。",
        "chapter_contract": contract,
        "boundary": ChapterBoundary(
            entry_state="主角进入现场",
            exit_state="主角停机并取得证据",
            ending_function="reveal",
            dialogue_closed=True,
            dramatic_unit_closed=True,
            estimated_chinese_chars=3400,
        ),
    }
    values.update(changes)
    return NovelReviewRequest(**values)


def test_reviewer_blocks_duplicate_long_paragraph():
    paragraph = "这是一段足够长的正文证据，用来确认跨章节复制不会被误认为普通短对白，同时必须被审查器稳定识别。"
    result = NovelReviewer().review(_request(
        draft=f"{paragraph}\n\n现场确认旧图缺失，试验暂停。",
        adjacent_drafts=(paragraph,),
    ))

    assert "duplicate_long_paragraph" in result.blocking_codes
    assert next(issue for issue in result.issues if issue.code == "duplicate_long_paragraph").evidence


def test_reviewer_blocks_character_state_drift_without_evidence():
    result = NovelReviewer().review(_request(character_changes=(
        CharacterStateProposal("林子轩", "从谨慎变为无条件服从", ()),
    )))

    assert "character_state_drift" in result.blocking_codes


def test_reviewer_preserves_timeline_and_foreshadow_findings():
    result = NovelReviewer().review(_request(consistency_findings=(
        ConsistencyFinding("timeline_conflict", "chapter", "人物在同一时间出现于两地"),
        ConsistencyFinding("foreshadow_lifecycle_break", "hook:signal", "伏笔在回收前被标记关闭"),
    )))

    assert set(result.blocking_codes) >= {"timeline_conflict", "foreshadow_lifecycle_break"}


def test_reviewer_blocks_missing_essential_story_information():
    result = NovelReviewer().review(_request(draft="主角进入现场，但正文没有呈现合同要求的信息。"))

    assert "essential_information_missing" in result.blocking_codes


def test_reviewer_passes_evidence_complete_draft():
    result = NovelReviewer().review(_request(character_changes=(
        CharacterStateProposal("林子轩", "承担停机代价", ("正文：林子轩承担停机代价",)),
    )))

    assert result.passed
    assert result.issues == ()
