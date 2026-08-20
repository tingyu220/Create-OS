from dataclasses import replace

import pytest

from creative_os.domains.narrative_decision import ReaderChange
from creative_os.domains.narrative_lifecycle import (
    HookStatus,
    LifecycleConflictError,
    build_emotional_history,
    build_hook_lifecycles,
    build_reader_expectation_history,
)
from creative_os.domains.novel_state_model import StateChange, StateEvidence
from tests.test_narrative_review import _decision


def _change(change_id, kind, subject, fields):
    return StateChange(change_id, kind, subject, "candidate", fields, [StateEvidence("chapter", "证据")])


def test_hook_lifecycle_tracks_progress_and_rejects_reopen_after_payoff():
    changes = [
        _change("chapter-003-hook-key", "hook", "key", {"status": "open", "question": "谁留下钥匙"}),
        _change("chapter-004-hook-key", "hook", "key", {"status": "advancing", "action": "发现钥匙算法"}),
        _change("chapter-005-hook-key", "hook", "key", {"status": "paid_off", "action": "确认钥匙来源"}),
    ]

    lifecycle = build_hook_lifecycles(changes)[0]

    assert lifecycle.status == HookStatus.PAID_OFF
    assert lifecycle.last_chapter == 5
    assert len(lifecycle.history) == 3

    with pytest.raises(LifecycleConflictError):
        build_hook_lifecycles(changes + [
            _change("chapter-006-hook-key", "hook", "key", {"status": "open", "action": "重新留下疑问"}),
        ])


def test_emotional_history_requires_structured_character_state():
    history = build_emotional_history([
        _change("chapter-003-character-main", "character", "主角", {"emotional_state": ["警觉", "抗拒"]}),
        _change("chapter-004-character-main", "character", "主角", {"emotional_state": ["动摇"]}),
    ])

    assert [(item.chapter, item.states) for item in history] == [(3, ("警觉", "抗拒")), (4, ("动摇",))]


def test_reader_expectation_history_requires_continuous_transition():
    first = _decision()
    second = _decision()
    second = second.with_chapter(
        8,
        chapter_contract=replace(
            second.chapter_contract,
            reader_change=ReaderChange("完全不同的预期", "新的判断"),
        ),
    )

    with pytest.raises(LifecycleConflictError, match="reader expectation"):
        build_reader_expectation_history([first, second])
