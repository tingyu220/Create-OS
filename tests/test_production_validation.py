import json
import re

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
    report = run_continuous_validation(project, client=FakeClient(), chapter_count=10, max_attempts=2, require_narrative_contract=False)

    assert report.status == "pass"
    assert report.completed_chapters == 10
    assert report.recovery_ok
    assert report.event_count == 90
    assert report.max_context_size_chars > 0
    assert (project / "production/reports/continuous_validation.json").exists()


def test_continuous_validation_stops_at_first_failed_chapter(tmp_path):
    project = _project(tmp_path)

    class FailingClient(FakeClient):
        def complete(self, messages, *, temperature, max_tokens):
            self.calls += 1
            return "# 第2章\n太短。"

    report = run_continuous_validation(project, client=FailingClient(), chapter_count=10, require_narrative_contract=False)

    assert report.status == "fail"
    assert report.completed_chapters == 0
    assert len(report.chapters) == 1


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

    report = run_continuous_validation(project, client=DriftClient(), chapter_count=1, require_narrative_contract=False)

    assert report.status == "pass"
    assert report.entity_warning_count == 1
    review = json.loads((project / ".creative_os/reviews/chapter_002_continuation.json").read_text(encoding="utf-8"))
    assert review["issues"] == []
    assert review["entity_warnings"][0]["observed"] == "刘子轩"


def test_recovery_passes_at_an_approved_contract_boundary(tmp_path):
    project = _project(tmp_path)
    from creative_os.domains.narrative_memory import save_narrative_candidate
    from creative_os.memory.approval import approve_candidate
    from creative_os.memory.model import MemoryEvidence
    from creative_os.memory.store import JsonMemoryStore
    from tests.test_narrative_memory import _decision

    item = save_narrative_candidate(project, _decision(2), evidence=[MemoryEvidence("test", "contract")])
    approve_candidate(JsonMemoryStore(project / ".creative_os/memory"), item.id, actor="tingyu", note="批准")

    report = run_continuous_validation(project, client=FakeClient(), chapter_count=1, require_narrative_contract=True)

    assert report.status == "pass"
    assert report.recovery_ok


def test_narrative_audit_requires_contract_context_review_and_complete_event_lifecycle(tmp_path):
    project = _project(tmp_path)
    (project / ".creative_os/contexts/compiled").mkdir(parents=True)
    (project / ".creative_os/reviews").mkdir(parents=True)
    from creative_os.domains.narrative_memory import save_narrative_candidate
    from creative_os.memory.approval import approve_candidate
    from creative_os.memory.model import MemoryEvidence
    from creative_os.memory.store import JsonMemoryStore
    from tests.test_narrative_memory import _decision
    from creative_os.runtime import AppendOnlyEventLog, EventType

    item = save_narrative_candidate(project, _decision(2), evidence=[MemoryEvidence("test", "contract")])
    store = JsonMemoryStore(project / ".creative_os/memory")
    approve_candidate(store, item.id, actor="tingyu", note="批准")
    (project / "production/final_chapters/chapter_002.md").write_text("# 第2章\n正文", encoding="utf-8")
    (project / ".creative_os/contexts/compiled/chapter_002.json").write_text(json.dumps({"size_chars": 100, "sources": [{"source_id": "narrative:chapter:002"}]}), encoding="utf-8")
    (project / ".creative_os/reviews/chapter_002_continuation.json").write_text('{"issues": []}', encoding="utf-8")
    log = AppendOnlyEventLog(project / ".creative_os/runtime/events.jsonl")
    for event_type in (EventType.TASK_CREATED, EventType.TASK_STARTED, EventType.CONTEXT_BUILT, EventType.CAPABILITY_CALLED, EventType.RESULT_GENERATED, EventType.REVIEW_PASSED, EventType.KNOWLEDGE_UPDATED, EventType.STATE_CHANGED, EventType.TASK_COMPLETED):
        log.append_simple(event_type, task_id="chapter-002", payload={})

    report = audit_narrative_production(project, first_chapter=2, last_chapter=2)

    assert report["passed"]
    assert (project / "production/reports/narrative_production_audit_002_002.json").exists()
