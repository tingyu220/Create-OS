from __future__ import annotations

from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import multiprocessing
import os

import pytest

from creative_os.domains.publication_migration_model import SourceFragment
from creative_os.domains.publication_source_snapshot import (
    build_source_snapshot,
    copy_verified_source_archive,
    load_verified_archive,
)
from creative_os.domains.publication_split_planner import (
    BoundaryStatus,
    ClosureDimension,
    ClosureEvidence,
    DramaticUnit,
    PublicationSplitPlanner,
    SourceChapterPlanningInput,
    SplitPlanCandidate,
    SplitPlanOmission,
    SplitPlanReviewRecord,
    SplitPlanningInputs,
    plan_source_chapters,
    split_plan_review_hash,
    split_plan_candidate_hash,
)
from creative_os.runtime.publication_split_approval_store import (
    SplitPlanApprovalConflict,
    SplitPlanApprovalIntegrityError,
    SplitPlanApprovalStore,
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _paragraph_text(chapter: int, ordinal: int) -> str:
    return (
        f"第{chapter}章第{ordinal}段，“对话已闭合。”冲突在现场解除。"
        "人物完成选择并承担后果。状态发生改变。章末信号亮起。"
    )


def _archive(root, *, chapter5_override: dict[int, str] | None = None, chapter5_count: int = 4):
    chapters = root / "production" / "final_chapters"
    chapters.mkdir(parents=True, exist_ok=True)
    for chapter in range(1, 33):
        count = chapter5_count if chapter == 5 else 2
        text = "\n\n".join(
            chapter5_override.get(ordinal, _paragraph_text(chapter, ordinal))
            if chapter == 5 and chapter5_override else _paragraph_text(chapter, ordinal)
            for ordinal in range(1, count + 1)
        )
        (chapters / f"chapter_{chapter:03d}.md").write_text(text, encoding="utf-8", newline="")
    snapshot = build_source_snapshot(root, 4, range(5, 33))
    receipt = copy_verified_source_archive(snapshot, root)
    return receipt, load_verified_archive(receipt, root)


def _unit(chapter: int, start: int, end: int, **changes: object) -> DramaticUnit:
    fragments = tuple(
        SourceFragment(chapter, index, index, _hash(_paragraph_text(chapter, index)))
        for index in range(start, end + 1)
    )
    last_hash = _hash(_paragraph_text(chapter, end))
    first_hash = _hash(_paragraph_text(chapter, start))
    def evidence(dimension, ordinal, paragraph_hash, excerpt):
        text = _paragraph_text(chapter, ordinal)
        offset = text.index(excerpt)
        return ClosureEvidence(
            dimension, chapter, ordinal, paragraph_hash, excerpt, offset, offset + len(excerpt),
        )
    values = {
        "function": "把异常从个人发现推进为组织危机",
        "scene_scope": ("射电阵列值班室",),
        "conflict": "是否立即封锁异常数据",
        "choice_or_discovery": "值班员选择保留原始记录",
        "outcome": "原始记录进入双人见证流程",
        "information_reveal": "异常同时出现在两组接收器",
        "technology_state": "接收器完成交叉校验，尚未解释信号来源",
        "state_shift": "异常从猜测变成可复核证据",
        "ending_hook": "第二组接收器同时亮起",
        "source_fragments": fragments,
        "estimated_chinese_chars": 3400,
        "boundary_basis": "dramatic_turn",
        "dialogue_closed": True,
        "conflict_status": BoundaryStatus.RESOLVED,
        "choice_status": BoundaryStatus.RESOLVED,
        "closure_evidence": (
            evidence(ClosureDimension.CONFLICT, start, first_hash, "冲突在现场解除"),
            evidence(ClosureDimension.DIALOGUE, end, last_hash, "“对话已闭合。”"),
            evidence(ClosureDimension.CHOICE, end, last_hash, "人物完成选择并承担后果"),
            evidence(ClosureDimension.STATE, end, last_hash, "状态发生改变"),
            evidence(ClosureDimension.HOOK, end, last_hash, "章末信号亮起"),
        ),
    }
    values.update(changes)
    return DramaticUnit(**values)


def _unit_for_texts(
    chapter: int, start: int, end: int, texts: dict[int, str], *, dialogue_excerpt: str,
) -> DramaticUnit:
    unit = _unit(chapter, start, end)
    fragments = tuple(
        SourceFragment(chapter, ordinal, ordinal, _hash(texts[ordinal]))
        for ordinal in range(start, end + 1)
    )
    evidence = []
    for item in unit.closure_evidence:
        text = texts[item.paragraph_ordinal]
        excerpt = dialogue_excerpt if item.dimension is ClosureDimension.DIALOGUE else item.excerpt
        offset = text.index(excerpt)
        evidence.append(replace(
            item, paragraph_hash=_hash(text), excerpt=excerpt,
            start_offset=offset, end_offset=offset + len(excerpt),
        ))
    return replace(unit, source_fragments=fragments, closure_evidence=tuple(evidence))


def _inputs(*units: DramaticUnit, omissions: tuple[SplitPlanOmission, ...] = ()) -> SplitPlanningInputs:
    chapter_five = tuple(units) or (_unit(5, 1, 2), _unit(5, 3, 4))
    return SplitPlanningInputs(
        migration_id="migration-publication-v2",
        target_edition_id="publication-v2",
        chapters=tuple(
            SourceChapterPlanningInput(
                source_chapter=chapter,
                contract_hash=_hash(f"contract-{chapter}"),
                pov_plan_hash=_hash(f"pov-{chapter}"),
                scene_plan_hash=_hash(f"scene-{chapter}"),
                units=chapter_five if chapter == 5 else (_unit(chapter, 1, 2),),
            )
            for chapter in range(5, 33)
        ),
        omissions=omissions,
    )


def _omission(source, chapter=5, *ordinals: int, **changes: object) -> SplitPlanOmission:
    ordinals = ordinals or (4,)
    values = {
        "source_fragments": tuple(
            SourceFragment(chapter, ordinal, ordinal, _hash(_paragraph_text(chapter, ordinal)))
            for ordinal in ordinals
        ),
        "snapshot_hash": source.snapshot_hash,
        "reason": "该段重复解释上一单元已经完成的接收器校验",
        "evidence": "相邻单元已保留相同校验结论",
        "impact": "不改变事件顺序、人物选择或技术状态",
    }
    values.update(changes)
    return SplitPlanOmission(**values)


def _candidate(receipt, root) -> SplitPlanCandidate:
    return plan_source_chapters(receipt, root, _inputs(_unit(5, 1, 2), _unit(5, 3, 4)))


def _review(receipt, root, candidate: SplitPlanCandidate | None = None):
    candidate = candidate or _candidate(receipt, root)
    return PublicationSplitPlanner().review_record(candidate, receipt, root)


def _process_append_candidate(root, candidate, receipt, review, queue):
    try:
        queue.put(("ok", SplitPlanApprovalStore(root).append_candidate(candidate, receipt, review)))
    except Exception as error:  # pragma: no cover - 仅跨进程回传错误
        queue.put(("error", type(error).__name__))


def _process_append_decision(root, candidate_hash, actor, reason, queue):
    try:
        decision = SplitPlanApprovalStore(root).append_decision(
            candidate_hash, actor, reason, True,
        )
        queue.put(("ok", decision.actor, decision.reason))
    except Exception as error:  # pragma: no cover - 仅跨进程回传错误
        queue.put(("error", type(error).__name__))


def test_split_planner_builds_deterministic_evidence_bound_candidate(tmp_path):
    receipt, source = _archive(tmp_path)
    inputs = _inputs(_unit(5, 1, 2), _unit(5, 3, 4))

    first = plan_source_chapters(receipt, tmp_path, inputs)
    second = plan_source_chapters(receipt, tmp_path, inputs)

    assert first == second
    assert first.project_id == tmp_path.name
    assert first.source_edition_id == source.source_edition_id
    assert first.target_edition_id == "publication-v2"
    assert first.source_snapshot_hash == source.snapshot_hash
    assert first.candidate_hash == split_plan_candidate_hash(first)
    assert PublicationSplitPlanner().review(first, receipt, tmp_path) == ()
    review = PublicationSplitPlanner().review_record(first, receipt, tmp_path)
    assert review.blocking_issues == ()
    assert review.review_hash == split_plan_review_hash(review)


def test_split_plan_omission_is_verified_and_completes_source_coverage(tmp_path):
    receipt, source = _archive(tmp_path)
    omission = _omission(source, 5, 4)
    candidate = plan_source_chapters(
        receipt, tmp_path, _inputs(_unit(5, 1, 3), omissions=(omission,)),
    )

    assert candidate.omissions == (omission,)
    assert PublicationSplitPlanner().review(candidate, receipt, tmp_path) == ()
    assert split_plan_candidate_hash(candidate) == candidate.candidate_hash


@pytest.mark.parametrize("tamper", ["hash", "locator", "snapshot", "unit_overlap", "omission_overlap"])
def test_split_plan_omission_rejects_forgery_and_overlap(tmp_path, tamper):
    receipt, source = _archive(tmp_path)
    omission = _omission(source, 5, 4)
    units = (_unit(5, 1, 3),)
    omissions = (omission,)
    if tamper == "hash":
        omission = replace(omission, source_fragments=(SourceFragment(5, 4, 4, _hash("伪造")),))
        omissions = (omission,)
    elif tamper == "locator":
        omission = replace(omission, source_fragments=(SourceFragment(5, 99, 99, _hash("伪造")),))
        omissions = (omission,)
    elif tamper == "snapshot":
        omissions = (replace(omission, snapshot_hash=_hash("伪快照")),)
    elif tamper == "unit_overlap":
        omission = _omission(source, 5, 3)
        omissions = (omission, _omission(source, 5, 4))
    else:
        omissions = (omission, omission)
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(*units, omissions=omissions))
    codes = {item.code for item in PublicationSplitPlanner().review(candidate, receipt, tmp_path)}
    assert codes & {"omission_snapshot_mismatch", "omission_source_mismatch",
                    "omission_source_overlap", "omission_source_out_of_order"}


def test_split_plan_omission_blocks_whole_chapter_or_large_scope(tmp_path):
    receipt, source = _archive(tmp_path)
    omission = _omission(source, 5, 1, 2, 3, 4)
    candidate = plan_source_chapters(
        receipt, tmp_path, _inputs(_unit(5, 1, 2), _unit(5, 3, 4), omissions=(omission,)),
    )
    assert "omission_scope_requires_review" in {
        item.code for item in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_plan_omission_scope_is_aggregated_across_multiple_records(tmp_path):
    receipt, source = _archive(tmp_path, chapter5_count=8)
    omissions = (_omission(source, 5, 3, 4, 5), _omission(source, 5, 6, 7, 8))
    candidate = plan_source_chapters(
        receipt, tmp_path, _inputs(_unit(5, 1, 2), omissions=omissions),
    )
    assert "omission_scope_requires_review" in {
        item.code for item in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_plan_omission_allows_small_aggregate_with_retained_unit(tmp_path):
    receipt, source = _archive(tmp_path, chapter5_count=8)
    omissions = (_omission(source, 5, 7), _omission(source, 5, 8))
    candidate = plan_source_chapters(
        receipt, tmp_path, _inputs(_unit(5, 1, 6), omissions=omissions),
    )
    assert PublicationSplitPlanner().review(candidate, receipt, tmp_path) == ()


def test_split_plan_omission_rejects_zero_unit_chapter_before_candidate(tmp_path):
    receipt, source = _archive(tmp_path)
    inputs = _inputs(_unit(5, 1, 3), omissions=(_omission(source, 5, 4),))
    chapters = tuple(
        replace(chapter, units=()) if chapter.source_chapter == 5 else chapter
        for chapter in inputs.chapters
    )
    with pytest.raises(ValueError, match="requires a retained dramatic unit"):
        plan_source_chapters(receipt, tmp_path, replace(inputs, chapters=chapters))


def test_split_plan_review_blocks_whole_chapter_split_into_small_omissions(tmp_path):
    receipt, source = _archive(tmp_path, chapter5_count=8)
    base = plan_source_chapters(receipt, tmp_path, _inputs(_unit(5, 1, 8)))
    chapter_five_unit = base.units[0]
    partial = replace(
        base,
        units=tuple(unit for unit in base.units if unit is not chapter_five_unit),
        omissions=(_omission(source, 5, 1, 2, 3, 4), _omission(source, 5, 5, 6, 7, 8)),
        candidate_hash="",
    )
    candidate = replace(partial, candidate_hash=split_plan_candidate_hash(partial))
    assert "omission_scope_requires_review" in {
        item.code for item in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_plan_omission_changes_candidate_hash_and_roundtrips_store(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = plan_source_chapters(
        receipt, tmp_path, _inputs(_unit(5, 1, 3), omissions=(_omission(source, 5, 4),)),
    )
    with pytest.raises(ValueError, match="candidate_hash mismatch"):
        replace(candidate, omissions=(replace(candidate.omissions[0], reason="改写理由"),))

    review = PublicationSplitPlanner().review_record(candidate, receipt, tmp_path)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    decision = store.append_decision(candidate.candidate_hash, "总控", "批准明确遗漏", True)
    recovered = SplitPlanApprovalStore(tmp_path).recover()
    assert recovered.candidates[0].omissions == candidate.omissions
    assert recovered.decisions == (decision,)


def test_split_planner_rejects_boundary_inside_open_dialogue_or_unresolved_choice(tmp_path):
    receipt, _ = _archive(tmp_path)
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(
            _unit(5, 1, 2, dialogue_closed=False, choice_or_discovery=""),
            _unit(5, 3, 4),
        ),
    )

    codes = {issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)}

    assert codes >= {"cut_inside_dialogue", "dramatic_unit_incomplete"}


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"boundary_basis": "character_count"}, "mechanical_length_cut"),
        ({"conflict": ""}, "dramatic_unit_incomplete"),
        ({"state_shift": ""}, "dramatic_unit_incomplete"),
        ({"ending_hook": ""}, "ending_hook_missing"),
        ({"source_fragments": ()}, "source_fragment_empty"),
        ({"scene_scope": ()}, "dramatic_unit_incomplete"),
        ({"outcome": ""}, "dramatic_unit_incomplete"),
        ({"information_reveal": ""}, "dramatic_unit_incomplete"),
        ({"technology_state": ""}, "dramatic_unit_incomplete"),
    ],
)
def test_split_planner_reports_each_fail_closed_boundary_issue(tmp_path, change, expected):
    receipt, _ = _archive(tmp_path)
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(_unit(5, 1, 2, **change), _unit(5, 3, 4)))
    assert expected in {issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)}


def test_split_planner_rejects_duplicate_out_of_order_and_source_hash_mismatch(tmp_path):
    receipt, _ = _archive(tmp_path)
    wrong_hash = SourceFragment(5, 2, 2, _hash("错误"))
    duplicate = replace(_unit(5, 3, 4), source_fragments=(wrong_hash, *_unit(5, 1, 2).source_fragments))
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(_unit(5, 1, 2), duplicate))

    codes = {issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)}

    assert codes >= {"source_fragment_duplicate", "source_fragment_out_of_order", "source_hash_mismatch"}


def test_split_planner_rejects_incomplete_source_coverage_and_stale_snapshot(tmp_path):
    receipt, _ = _archive(tmp_path)
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(_unit(5, 1, 2)))

    assert "source_fragment_missing" in {
        issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"conflict": "冲突未解决"},
        {"choice_or_discovery": "林子轩尚未决定是否上报"},
        {"choice_or_discovery": "等待选择"},
        {"closure_evidence": ()},
        {"closure_evidence": (
            ClosureEvidence(ClosureDimension.DIALOGUE, 5, 1, _hash("错误"), "伪造", 0, 2),
        )},
    ],
)
def test_split_planner_rejects_structurally_unresolved_causal_boundary(tmp_path, changes):
    receipt, _ = _archive(tmp_path)
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(_unit(5, 1, 2, **changes), _unit(5, 3, 4)))
    codes = {issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)}
    assert "dramatic_unit_incomplete" in codes or "boundary_evidence_invalid" in codes


@pytest.mark.parametrize("tamper", ["locator", "hash", "excerpt", "reuse"])
def test_split_planner_rejects_forged_or_reused_closure_evidence(tmp_path, tamper):
    receipt, _ = _archive(tmp_path)
    unit = _unit(5, 1, 2)
    evidence = list(unit.closure_evidence)
    if tamper == "locator":
        evidence[0] = replace(evidence[0], paragraph_ordinal=99)
    elif tamper == "hash":
        evidence[0] = replace(evidence[0], paragraph_hash=_hash("伪造"))
    elif tamper == "excerpt":
        evidence[0] = replace(evidence[0], excerpt="正文中不存在")
    else:
        evidence = [
            replace(evidence[0], dimension=dimension)
            for dimension in ClosureDimension
        ]
    candidate = plan_source_chapters(
        receipt, tmp_path, _inputs(replace(unit, closure_evidence=tuple(evidence)), _unit(5, 3, 4)),
    )
    assert "boundary_evidence_invalid" in {
        issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_planner_reads_actual_archive_text_to_reject_open_dialogue(tmp_path):
    open_text = (
        "第5章第2段，“对话未闭合。冲突在现场解除。"
        "人物完成选择并承担后果。状态发生改变。章末信号亮起。"
    )
    receipt, _ = _archive(tmp_path, chapter5_override={2: open_text})
    texts = {1: _paragraph_text(5, 1), 2: open_text}
    unit = _unit_for_texts(5, 1, 2, texts, dialogue_excerpt="对话未闭合")
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(unit, _unit(5, 3, 4)),
    )
    assert "boundary_evidence_invalid" in {
        issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


@pytest.mark.parametrize(
    "dialogue",
    [
        "”旧对话结束。然后“新对话开启",
        '"只有一个ASCII引号',
    ],
)
def test_split_planner_quote_state_machine_rejects_wrong_order_or_odd_ascii(tmp_path, dialogue):
    second = (
        f"第5章第2段，{dialogue}。冲突在现场解除。"
        "人物完成选择并承担后果。状态发生改变。章末信号亮起。"
    )
    receipt, _ = _archive(tmp_path, chapter5_override={2: second})
    texts = {1: _paragraph_text(5, 1), 2: second}
    unit = _unit_for_texts(5, 1, 2, texts, dialogue_excerpt="章末信号亮起")
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(unit, _unit(5, 3, 4)))
    assert "boundary_evidence_invalid" in {
        issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_planner_quote_state_machine_accepts_nested_and_consecutive_dialogue(tmp_path):
    second = (
        "第5章第2段，“外层‘内层’结束”“连续对话”。冲突在现场解除。"
        "人物完成选择并承担后果。状态发生改变。章末信号亮起。"
    )
    receipt, _ = _archive(tmp_path, chapter5_override={2: second})
    unit = _unit_for_texts(
        5, 1, 2, {1: _paragraph_text(5, 1), 2: second}, dialogue_excerpt="“连续对话”",
    )
    candidate = plan_source_chapters(receipt, tmp_path, _inputs(unit, _unit(5, 3, 4)))
    assert PublicationSplitPlanner().review(candidate, receipt, tmp_path) == ()


def test_split_planner_rejects_nested_or_partial_overlap_evidence_spans(tmp_path):
    receipt, _ = _archive(tmp_path)
    unit = _unit(5, 1, 2)
    evidence = list(unit.closure_evidence)
    state = next(item for item in evidence if item.dimension is ClosureDimension.STATE)
    hook_index = next(index for index, item in enumerate(evidence) if item.dimension is ClosureDimension.HOOK)
    paragraph = _paragraph_text(5, 2)
    nested_excerpt = "状态发生改变。"
    nested_start = paragraph.index(nested_excerpt)
    evidence[hook_index] = replace(
        evidence[hook_index], excerpt=nested_excerpt,
        start_offset=nested_start, end_offset=nested_start + len(nested_excerpt),
    )
    assert state.start_offset == nested_start
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(replace(unit, closure_evidence=tuple(evidence)), _unit(5, 3, 4)),
    )
    assert "boundary_evidence_invalid" in {
        issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_planner_uses_offsets_to_disambiguate_repeated_excerpt(tmp_path):
    repeated = (
        "第5章第2段，“对话已闭合。”冲突在现场解除。人物完成选择并承担后果。"
        "状态发生改变。章末信号亮起。中间状态。章末信号亮起。"
    )
    receipt, _ = _archive(tmp_path, chapter5_override={2: repeated})
    unit = _unit_for_texts(
        5, 1, 2, {1: _paragraph_text(5, 1), 2: repeated}, dialogue_excerpt="“对话已闭合。”",
    )
    positions = []
    cursor = 0
    while True:
        found = repeated.find("章末信号亮起", cursor)
        if found < 0:
            break
        positions.append(found)
        cursor = found + 1
    evidence = []
    for item in unit.closure_evidence:
        if item.dimension is ClosureDimension.STATE:
            evidence.append(replace(
                item, excerpt="章末信号亮起", start_offset=positions[0],
                end_offset=positions[0] + len("章末信号亮起"),
            ))
        elif item.dimension is ClosureDimension.HOOK:
            evidence.append(replace(
                item, excerpt="章末信号亮起", start_offset=positions[1],
                end_offset=positions[1] + len("章末信号亮起"),
            ))
        else:
            evidence.append(item)
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(replace(unit, closure_evidence=tuple(evidence)), _unit(5, 3, 4)),
    )
    assert PublicationSplitPlanner().review(candidate, receipt, tmp_path) == ()


@pytest.mark.parametrize(
    "span_change", [{"start_offset": 999, "end_offset": 1005}, {"start_offset": 1}],
)
def test_split_planner_rejects_out_of_bounds_or_misaligned_evidence_span(tmp_path, span_change):
    receipt, _ = _archive(tmp_path)
    unit = _unit(5, 1, 2)
    evidence = list(unit.closure_evidence)
    evidence[0] = replace(evidence[0], **span_change)
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(replace(unit, closure_evidence=tuple(evidence)), _unit(5, 3, 4)),
    )
    assert "boundary_evidence_invalid" in {
        issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)
    }


def test_split_planner_rejects_any_frozen_chapter_fragment(tmp_path):
    receipt, _ = _archive(tmp_path)
    unit = _unit(5, 1, 2)
    frozen = SourceFragment(4, 1, 1, _hash(_paragraph_text(4, 1)))
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(replace(unit, source_fragments=(frozen, *unit.source_fragments)), _unit(5, 3, 4)),
    )
    codes = {issue.code for issue in PublicationSplitPlanner().review(candidate, receipt, tmp_path)}
    assert codes >= {"source_hash_mismatch", "frozen_source_fragment_forbidden"}


def test_planner_input_fingerprint_changes_with_contract_pov_or_scene(tmp_path):
    receipt, _ = _archive(tmp_path)
    baseline = _inputs(_unit(5, 1, 2), _unit(5, 3, 4))
    candidate = plan_source_chapters(receipt, tmp_path, baseline)

    for field in ("contract_hash", "pov_plan_hash", "scene_plan_hash"):
        changed_chapter = replace(baseline.chapters[0], **{field: _hash(field)})
        chapters = (changed_chapter, *baseline.chapters[1:])
        changed = plan_source_chapters(receipt, tmp_path, replace(baseline, chapters=chapters))
        assert changed.input_fingerprint != candidate.input_fingerprint
        assert changed.candidate_hash != candidate.candidate_hash


def test_approval_store_binds_candidate_snapshot_actor_reason_and_decision_hash(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)

    decision = store.append_decision(
        candidate.candidate_hash,
        actor="总控",
        reason="戏剧节点与来源覆盖审核通过",
        approved=True,
        decided_at="2026-08-28T12:00:00+00:00",
    )

    assert decision.candidate_hash == candidate.candidate_hash
    assert decision.snapshot_hash == candidate.source_snapshot_hash
    assert len(decision.decision_hash) == 64
    assert decision.review_hash == review.review_hash
    assert store.require_current_approval(candidate, receipt, review) == decision

    reopened = SplitPlanApprovalStore(tmp_path)
    assert reopened.require_current_approval(candidate, receipt, review) == decision


def test_approval_store_is_idempotent_and_rejects_conflicting_decision(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    first = store.append_decision(
        candidate.candidate_hash, "总控", "批准", True, decided_at="2026-08-28T12:00:00+00:00"
    )
    assert store.append_decision(
        candidate.candidate_hash, "总控", "批准", True, decided_at="2026-08-28T13:00:00+00:00"
    ) == first
    with pytest.raises(SplitPlanApprovalConflict, match="decision_conflict"):
        store.append_decision(
            candidate.candidate_hash, "另一人", "拒绝", False, decided_at="2026-08-28T13:00:00+00:00"
        )


def test_approval_store_rejects_non_iso_or_timezone_free_decision_time(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, _review(receipt, tmp_path, candidate))

    for invalid in ("tomorrow", "2026-08-28T12:00:00"):
        with pytest.raises(ValueError, match="decided_at"):
            store.append_decision(candidate.candidate_hash, "总控", "批准", True, decided_at=invalid)


def test_approval_store_rejects_stale_candidate_and_candidate_tampering(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    store.append_decision(candidate.candidate_hash, "总控", "批准", True)
    newer = replace(candidate, target_edition_id="publication-v3", candidate_hash="")
    newer = replace(newer, candidate_hash=split_plan_candidate_hash(newer))
    newer_review = PublicationSplitPlanner().review_record(newer, receipt, tmp_path)
    store.append_candidate(newer, receipt, newer_review)

    with pytest.raises(SplitPlanApprovalIntegrityError, match="candidate_stale"):
        store.require_current_approval(candidate, receipt, review)
    with pytest.raises(SplitPlanApprovalIntegrityError, match="decision_missing"):
        store.require_current_approval(newer, receipt, newer_review)

    records_path = tmp_path / ".creative_os" / "publication_migration" / "split_approvals" / "records.jsonl"
    raw = records_path.read_text(encoding="utf-8")
    records_path.write_text(raw.replace(candidate.candidate_hash, "f" * 64, 1), encoding="utf-8")
    with pytest.raises(SplitPlanApprovalIntegrityError, match="tampered_records"):
        SplitPlanApprovalStore(tmp_path).recover()


def test_rejected_candidate_never_counts_as_approved(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    store.append_decision(candidate.candidate_hash, "总控", "需调整", False)

    with pytest.raises(SplitPlanApprovalIntegrityError, match="candidate_not_approved"):
        store.require_current_approval(candidate, receipt, review)


def test_approval_store_cannot_approve_blocking_or_forged_clean_review(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = plan_source_chapters(
        receipt, tmp_path,
        _inputs(_unit(5, 1, 2, conflict_status=BoundaryStatus.OPEN), _unit(5, 3, 4)),
    )
    review = PublicationSplitPlanner().review_record(candidate, receipt, tmp_path)
    assert review.blocking_issues
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    with pytest.raises(SplitPlanApprovalIntegrityError, match="review_blocking"):
        store.append_decision(candidate.candidate_hash, "总控", "不能绕过", True)

    forged_partial = SplitPlanReviewRecord(
        candidate_hash=candidate.candidate_hash,
        snapshot_hash=source.snapshot_hash,
        ruleset_version=review.ruleset_version,
        blocking_issues=(),
    )
    forged = replace(forged_partial, review_hash=split_plan_review_hash(forged_partial))
    with pytest.raises(SplitPlanApprovalIntegrityError, match="review_binding_invalid"):
        store.append_candidate(candidate, receipt, forged)


def test_approval_store_rejects_even_self_consistent_caller_snapshot_as_authority(tmp_path):
    receipt, _ = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    caller_snapshot = build_source_snapshot(tmp_path, 4, range(5, 33))

    with pytest.raises((TypeError, ValueError)):
        SplitPlanApprovalStore(tmp_path).append_candidate(candidate, caller_snapshot, review)


def test_approval_store_rejects_stale_ruleset_review_on_reload(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    store.append_decision(candidate.candidate_hash, "总控", "批准", True)
    stale_partial = SplitPlanReviewRecord(
        candidate_hash=candidate.candidate_hash,
        snapshot_hash=source.snapshot_hash,
        ruleset_version="publication-split-review-old",
        blocking_issues=(),
    )
    stale = replace(stale_partial, review_hash=split_plan_review_hash(stale_partial))
    with pytest.raises(SplitPlanApprovalIntegrityError, match="review_binding_invalid"):
        store.require_current_approval(candidate, receipt, stale)


def test_planner_rejects_forged_authority_receipt(tmp_path):
    receipt, _ = _archive(tmp_path)
    forged = replace(receipt, source_snapshot_hash=_hash("伪造快照"))
    with pytest.raises(ValueError):
        plan_source_chapters(forged, tmp_path, _inputs(_unit(5, 1, 2), _unit(5, 3, 4)))


def test_approval_store_does_not_heal_unrelated_tampered_head_even_with_journal(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    head_path = tmp_path / ".creative_os" / "publication_migration" / "split_approvals" / "head.json"
    head_path.write_bytes(
        (json.dumps({"count": 99, "head_hash": "f" * 64}, separators=(",", ":")) + "\n").encode("utf-8")
    )

    with pytest.raises(SplitPlanApprovalIntegrityError, match="tampered_head"):
        SplitPlanApprovalStore(tmp_path).recover()


def test_approval_store_recovers_prepared_decision_after_restart(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    decision = store.append_decision(candidate.candidate_hash, "总控", "批准", True)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    records_path = root / "records.jsonl"
    envelopes = records_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(envelopes[0])
    records_path.write_bytes((envelopes[0] + "\n").encode("utf-8"))
    (root / "head.json").write_bytes(
        (json.dumps(
            {"count": first["sequence"], "head_hash": first["envelope_hash"]},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n").encode("utf-8")
    )

    assert SplitPlanApprovalStore(tmp_path).require_current_approval(candidate, receipt, review) == decision


def test_approval_store_serializes_concurrent_idempotent_candidate_and_decision(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    stores = [SplitPlanApprovalStore(tmp_path) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        hashes = tuple(pool.map(lambda store: store.append_candidate(candidate, receipt, review), stores))
    assert hashes == (candidate.candidate_hash,) * 4
    with ThreadPoolExecutor(max_workers=4) as pool:
        decisions = tuple(pool.map(
            lambda store: store.append_decision(candidate.candidate_hash, "总控", "并发批准", True),
            stores,
        ))
    assert len({item.decision_hash for item in decisions}) == 1
    recovered = SplitPlanApprovalStore(tmp_path).recover()
    assert len(recovered.candidates) == 1
    assert len(recovered.decisions) == 1


def test_approval_store_serializes_concurrent_conflicting_decisions(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)

    def decide(actor):
        local = SplitPlanApprovalStore(tmp_path)
        try:
            return local.append_decision(candidate.candidate_hash, actor, f"{actor}裁决", True)
        except SplitPlanApprovalConflict as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(decide, ("甲", "乙")))
    assert sum(not isinstance(item, Exception) for item in results) == 1
    assert sum(isinstance(item, SplitPlanApprovalConflict) for item in results) == 1


def test_approval_store_serializes_two_cross_process_writers(tmp_path):
    receipt, _ = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(
            target=_process_append_candidate,
            args=(tmp_path, candidate, receipt, review, queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    results = tuple(queue.get(timeout=30) for _ in processes)
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    assert results == (("ok", candidate.candidate_hash),) * 2
    assert len(SplitPlanApprovalStore(tmp_path).recover().candidates) == 1


def test_approval_store_cross_process_conflicting_decisions_have_one_exact_winner(tmp_path):
    receipt, _ = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    SplitPlanApprovalStore(tmp_path).append_candidate(candidate, receipt, review)
    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    processes = [
        context.Process(
            target=_process_append_decision,
            args=(tmp_path, candidate.candidate_hash, actor, f"{actor}理由", queue),
        )
        for actor in ("甲", "乙")
    ]
    for process in processes:
        process.start()
    results = tuple(queue.get(timeout=30) for _ in processes)
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0
    assert sum(item[0] == "ok" for item in results) == 1
    assert sum(item == ("error", "SplitPlanApprovalConflict") for item in results) == 1
    reopened = SplitPlanApprovalStore(tmp_path)
    recovery = reopened.recover()
    assert len(recovery.decisions) == 1
    winner = next(item for item in results if item[0] == "ok")
    assert (recovery.decisions[0].actor, recovery.decisions[0].reason) == winner[1:]
    assert reopened.require_current_approval(candidate, receipt, review) == recovery.decisions[0]


def test_approval_store_fails_closed_after_trusted_store_root_replacement(tmp_path, monkeypatch):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    moved = root.with_name("split_approvals_moved")
    try:
        root.rename(moved)
    except PermissionError:
        # Windows 持久目录句柄阻止真实替换；probe 继续证明身份漂移分支会拒绝。
        original = store._filesystem._named_directory_identity
        calls = []
        def drift(path):
            calls.append(path)
            identity = original(path)
            return (identity[0], identity[1] + 1) if path == root else identity
        monkeypatch.setattr(store._filesystem, "_named_directory_identity", drift)
        with pytest.raises(SplitPlanApprovalIntegrityError):
            store.recover()
        assert root in calls
        return
    root.mkdir()

    with pytest.raises(SplitPlanApprovalIntegrityError):
        store.recover()


def test_approval_store_rejects_live_records_file_replacement(tmp_path):
    receipt, _ = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    replacement = root / "records.replacement"
    replacement.write_bytes(b'{"forged":true}\n')
    os.replace(replacement, root / "records.jsonl")
    with pytest.raises(SplitPlanApprovalIntegrityError, match="tampered_records"):
        store.recover()


def test_approval_store_rejects_live_lock_file_replacement_or_identity_probe(tmp_path, monkeypatch):
    receipt, _ = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    lock_path = root / ".split-plan-approval.lock"
    replacement = root / "lock.replacement"
    replacement.write_bytes(b"forged")
    try:
        os.replace(replacement, lock_path)
    except PermissionError:
        calls = []
        original = store._filesystem._validate_named_file
        def reject_lock(path, identity):
            calls.append(path)
            if path == lock_path:
                raise SplitPlanApprovalIntegrityError("lock_identity_changed")
            return original(path, identity)
        monkeypatch.setattr(store._filesystem, "_validate_named_file", reject_lock)
    with pytest.raises(SplitPlanApprovalIntegrityError):
        store.recover()
    if 'calls' in locals():
        assert lock_path in calls


def test_approval_store_recovers_candidate_from_journal_only(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    store.close()
    (root / "records.jsonl").rename(root / "records.before-crash")
    (root / "head.json").rename(root / "head.before-crash")

    recovered = SplitPlanApprovalStore(tmp_path).recover()
    assert recovered.candidates == (candidate,)


@pytest.mark.parametrize("record_kind", ["candidate", "decision"])
@pytest.mark.parametrize("crash_state", ["journal_prepared", "record_written", "head_written"])
def test_approval_store_recovers_each_record_kind_at_each_journal_state(
    tmp_path, record_kind, crash_state,
):
    receipt, _ = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    decision = None
    if record_kind == "decision":
        decision = store.append_decision(candidate.candidate_hash, "总控", "批准", True)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    store.close()
    records_path = root / "records.jsonl"
    head_path = root / "head.json"
    lines = records_path.read_text(encoding="utf-8").splitlines()
    prior_lines = lines[:-1]
    if crash_state == "journal_prepared":
        if prior_lines:
            records_path.write_bytes(("\n".join(prior_lines) + "\n").encode("utf-8"))
        else:
            records_path.rename(root / f"records.{record_kind}.before-crash")
    if crash_state in {"journal_prepared", "record_written"}:
        if prior_lines:
            prior = json.loads(prior_lines[-1])
            head_path.write_bytes((json.dumps(
                {"count": prior["sequence"], "head_hash": prior["envelope_hash"]},
                sort_keys=True, separators=(",", ":"),
            ) + "\n").encode("utf-8"))
        else:
            head_path.rename(root / f"head.{record_kind}.before-crash")

    first = SplitPlanApprovalStore(tmp_path).recover()
    second = SplitPlanApprovalStore(tmp_path).recover()
    assert len(first.candidates) == len(second.candidates) == 1
    assert len(first.decisions) == len(second.decisions) == (1 if record_kind == "decision" else 0)
    if decision is not None:
        assert first.decisions == second.decisions == (decision,)
        with pytest.raises(SplitPlanApprovalConflict, match="decision_conflict"):
            SplitPlanApprovalStore(tmp_path).append_decision(
                candidate.candidate_hash, "其他人", "冲突决定", True,
            )
    else:
        assert SplitPlanApprovalStore(tmp_path).append_candidate(candidate, receipt, review) == candidate.candidate_hash


@pytest.mark.parametrize("record_kind", ["candidate", "decision"])
def test_approval_store_rejects_truncated_journal_and_records(tmp_path, record_kind):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    if record_kind == "decision":
        store.append_decision(candidate.candidate_hash, "总控", "批准", True)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    store.close()
    (root / "journal.json").write_bytes(b'{"state":"prepared"')
    with pytest.raises(SplitPlanApprovalIntegrityError, match="tampered_journal"):
        SplitPlanApprovalStore(tmp_path).recover()

    (root / "journal.json").write_bytes(b'{"state":"prepared"')
    (root / "records.jsonl").write_bytes(b'{"truncated":')
    with pytest.raises(SplitPlanApprovalIntegrityError, match="tampered_records"):
        SplitPlanApprovalStore(tmp_path).recover()


def test_approval_store_rejects_records_symlink_without_touching_target(tmp_path):
    receipt, source = _archive(tmp_path)
    candidate = _candidate(receipt, tmp_path)
    review = _review(receipt, tmp_path, candidate)
    store = SplitPlanApprovalStore(tmp_path)
    store.append_candidate(candidate, receipt, review)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    store.close()
    records = root / "records.jsonl"
    records.rename(root / "records.safe-backup")
    outside = tmp_path / "outside.jsonl"
    outside.write_bytes(b"outside-unchanged")
    try:
        os.symlink(outside, records)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")

    with pytest.raises(SplitPlanApprovalIntegrityError):
        SplitPlanApprovalStore(tmp_path).recover()
    assert outside.read_bytes() == b"outside-unchanged"


def test_approval_store_rejects_lock_symlink_without_touching_target(tmp_path):
    store = SplitPlanApprovalStore(tmp_path)
    root = tmp_path / ".creative_os" / "publication_migration" / "split_approvals"
    store.close()
    lock_path = root / ".split-plan-approval.lock"
    if lock_path.exists():
        lock_path.rename(root / ".split-plan-approval.safe-backup")
    outside = tmp_path / "outside.lock"
    outside.write_bytes(b"outside-unchanged")
    try:
        os.symlink(outside, lock_path)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")

    attacked = SplitPlanApprovalStore(tmp_path)
    with pytest.raises(SplitPlanApprovalIntegrityError):
        attacked.recover()
    assert outside.read_bytes() == b"outside-unchanged"
