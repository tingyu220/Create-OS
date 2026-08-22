import json
import re

import pytest

from creative_os.production_validation import audit_narrative_production, run_continuous_validation


class FakeClient:
    def __init__(self):
        self.calls = 0

    def complete(self, messages, *, temperature, max_tokens):
        self.calls += 1
        chapter = next(line for line in messages[-1].content.splitlines() if line.startswith("续写小说第"))
        number = re.search(r"第\s*(\d+)\s*章", chapter).group(1)
        return f"# 第{number}章\n" + "正文" * 3000


def _project(tmp_path):
    project = tmp_path / "validation"
    (project / "production/final_chapters").mkdir(parents=True)
    (project / ".creative_os/import").mkdir(parents=True)
    (project / "production/final_chapters/chapter_001.md").write_text("# 第1章\n结尾。", encoding="utf-8")
    (project / ".creative_os/import/baseline.json").write_text(
        json.dumps({"world_rules": [], "characters": [], "plot_milestones": [], "hooks": [], "style_constraints": []}), encoding="utf-8"
    )
    (project / ".creative_os/import/conflicts.json").write_text("[]", encoding="utf-8")
    (project / ".creative_os/import/approval.json").write_text('{"resolutions": {}}', encoding="utf-8")
    return project


def test_continuous_validation_runs_ten_chapters_and_writes_report(tmp_path):
    project = _project(tmp_path)
    with pytest.raises(TypeError):
        run_continuous_validation(project, client=FakeClient())
    assert not (project / "production/reports/continuous_validation.json").exists()


def test_continuous_validation_stops_at_first_failed_chapter(tmp_path):
    project = _project(tmp_path)

    class FailingClient(FakeClient):
        def complete(self, messages, *, temperature, max_tokens):
            self.calls += 1
            return "# 第2章\n太短。"

    with pytest.raises(TypeError):
        run_continuous_validation(project, client=FailingClient())


def test_entity_warning_is_reported_without_blocking_chapter(tmp_path):
    project = _project(tmp_path)
    baseline_path = project / ".creative_os/import/baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["characters"] = [{"title": "林子轩", "content": "---\nname: 林子轩\n---"}]
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")

    class DriftClient(FakeClient):
        def complete(self, messages, *, temperature, max_tokens):
            self.calls += 1
            chapter = next(line for line in messages[-1].content.splitlines() if line.startswith("续写小说第"))
            number = re.search(r"第\s*(\d+)\s*章", chapter).group(1)
            return f"# 第{number}章\n刘子轩" + "正文" * 3000

    with pytest.raises(TypeError):
        run_continuous_validation(project, client=DriftClient())


def test_legacy_approved_contract_does_not_enable_continuous_writer(tmp_path):
    project = _project(tmp_path)
    from creative_os.domains.narrative_memory import save_narrative_candidate
    from creative_os.memory.approval import approve_candidate
    from creative_os.memory.model import MemoryEvidence
    from creative_os.memory.store import JsonMemoryStore
    from tests.test_narrative_memory import _decision

    item = save_narrative_candidate(project, _decision(2), evidence=[MemoryEvidence("test", "contract")])
    approve_candidate(JsonMemoryStore(project / ".creative_os/memory"), item.id, actor="tingyu", note="批准")

    with pytest.raises(TypeError):
        run_continuous_validation(project, client=FakeClient())


def test_narrative_audit_requires_contract_context_review_and_complete_event_lifecycle(tmp_path):
    project = _project(tmp_path)
    (project / ".creative_os/contexts/compiled").mkdir(parents=True)
    (project / ".creative_os/reviews").mkdir(parents=True)
    from creative_os.runtime import AppendOnlyEventLog, EventType

    from creative_os.domains.contract_lifecycle import ContractLifecycleCoordinator
    from creative_os.domains.narrative_codec import NarrativeDecisionCodec
    from creative_os.domains.narrative_memory import build_narrative_candidate_item
    from creative_os.memory.model import MemoryEvidence
    from tests.test_narrative_memory import _decision
    from tests.test_writer_run_continuation import _pointer
    decision = _decision(2)
    lifecycle = ContractLifecycleCoordinator(project)
    lifecycle.store.add_immutable(build_narrative_candidate_item(
        project, decision, evidence=(MemoryEvidence("test", "fixture"),),
        item_id=f"{decision.contract_id}-v0001",
    ).activate(actor="editor"))
    pointer = _pointer(decision)
    lifecycle.write_pointer(pointer)
    fingerprint = "f" * 64
    (project / "production/final_chapters/chapter_002.md").write_text("# 第2章\n正文", encoding="utf-8")
    (project / ".creative_os/contexts/compiled/chapter_002.json").write_text(json.dumps({
        "size_chars": 100, "fingerprint": fingerprint,
        "contract_binding": {"contract_id": decision.contract_id,
            "contract_version": decision.contract_version,
            "contract_content_hash": NarrativeDecisionCodec.content_hash(decision),
            "context_fingerprint": fingerprint},
    }), encoding="utf-8")
    (project / ".creative_os/reviews/chapter_002_continuation.json").write_text(
        json.dumps({"issues": [], "context": fingerprint}), encoding="utf-8",
    )
    log = AppendOnlyEventLog(project / ".creative_os/runtime/events.jsonl")
    for event_type in (EventType.TASK_CREATED, EventType.TASK_STARTED, EventType.CONTEXT_BUILT, EventType.CAPABILITY_CALLED, EventType.RESULT_GENERATED, EventType.REVIEW_PASSED, EventType.KNOWLEDGE_UPDATED, EventType.STATE_CHANGED, EventType.TASK_COMPLETED):
        payload = ({"context_id": fingerprint} if event_type in {
            EventType.CONTEXT_BUILT, EventType.CAPABILITY_CALLED, EventType.RESULT_GENERATED
        } else {})
        log.append_simple(event_type, task_id="chapter-002", payload=payload)

    report = audit_narrative_production(project, first_chapter=2, last_chapter=2)

    assert report["passed"]
    assert (project / "production/reports/narrative_production_audit_002_002.json").exists()
    context_path = project / ".creative_os/contexts/compiled/chapter_002.json"
    tampered = json.loads(context_path.read_text(encoding="utf-8"))
    tampered["fingerprint"] = tampered["contract_binding"]["context_fingerprint"] = "0" * 64
    context_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert audit_narrative_production(project, first_chapter=2, last_chapter=2)["passed"] is False
    context_path.write_text(json.dumps({
        **tampered, "fingerprint": fingerprint,
        "contract_binding": {**tampered["contract_binding"],
                             "context_fingerprint": fingerprint},
    }), encoding="utf-8")
    log.append_simple(EventType.CAPABILITY_CALLED, task_id="chapter-002",
                      payload={"context_id": "0" * 64})
    assert audit_narrative_production(project, first_chapter=2, last_chapter=2)["passed"] is False


def test_narrative_audit_rejects_forged_context_without_authority(tmp_path):
    project = _project(tmp_path)
    (project / ".creative_os/contexts/compiled").mkdir(parents=True)
    (project / ".creative_os/reviews").mkdir(parents=True)
    (project / "production/final_chapters/chapter_002.md").write_text("正文", encoding="utf-8")
    fingerprint = "f" * 64
    (project / ".creative_os/contexts/compiled/chapter_002.json").write_text(json.dumps({
        "fingerprint": fingerprint, "contract_binding": {
            "contract_id": "narrative-chapter-002", "contract_version": 1,
            "contract_content_hash": "a" * 64, "context_fingerprint": fingerprint,
        },
    }), encoding="utf-8")
    (project / ".creative_os/reviews/chapter_002_continuation.json").write_text(
        json.dumps({"issues": [], "context": fingerprint}), encoding="utf-8",
    )
    assert audit_narrative_production(project, first_chapter=2, last_chapter=2)["passed"] is False
