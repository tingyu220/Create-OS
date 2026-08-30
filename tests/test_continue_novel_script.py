import json
import hashlib
from dataclasses import asdict, replace
from types import SimpleNamespace

import creative_os.novel_continuation_runner as runner
import pytest
from creative_os.llm_metrics import TimedCompletion
from creative_os.novel_continuation_runner import (
    PreparedWriterRun,
    continue_one_chapter as _secure_continue_one_chapter,
    promote_passing_draft as _secure_promote_passing_draft,
)
from creative_os.domains.writer_admission import AdmittedContractProjection, WriterAdmissionService, WriterAdmissionToken
from creative_os.domains.narrative_codec import NarrativeDecisionCodec
from tests.test_narrative_memory import _decision
from creative_os.foundation.knowledge import KnowledgeItem


@pytest.fixture(autouse=True)
def _unit_writer_handoff(monkeypatch):
    monkeypatch.setattr(WriterAdmissionService, "validate_token",
                        lambda self, _token, _run_id, _fingerprint, *, handoff: handoff())


def _prepared(project, *, target_chinese_chars=None):
    task, context = runner.build_next_chapter(project, target_chinese_chars=target_chinese_chars)
    decision = _decision(task.chapter_number)
    contract_hash = NarrativeDecisionCodec.content_hash(decision)
    projection = AdmittedContractProjection(decision.contract_id, decision.contract_version,
                                             contract_hash, NarrativeDecisionCodec.encode_v2(decision))
    task = replace(task, contract_projection=projection)
    task_hash = hashlib.sha256(json.dumps(asdict(task), ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest()
    context.knowledge[:] = [
        KnowledgeItem(item.id, item.kind, item.title, task_hash, category=item.category,
                      tags=item.tags, references=item.references, status=item.status,
                      source_task_id=item.source_task_id)
        if item.id == f"writer-task:chapter:{task.chapter_number:03d}" else item
        for item in context.knowledge
    ]
    projection_hash = hashlib.sha256(json.dumps(asdict(projection), ensure_ascii=False, sort_keys=True,
                                                separators=(",", ":")).encode()).hexdigest()
    token = WriterAdmissionToken(
        "writer_admission_token", "grant", project.name, f"chapter_{task.chapter_number:03d}",
        projection.contract_id, projection.contract_version, contract_hash, "b" * 64, "c" * 64, "d" * 64, "e" * 64,
        "f" * 64, "rules", (), "1" * 64, projection_hash, "2" * 64, context.fingerprint,
        "test-run", "2026-08-22T00:00:00+00:00", "2026-08-23T00:00:00+00:00", "signature",
    )
    return PreparedWriterRun(project, "test-run", task, context, projection, token,
                             WriterAdmissionService(project, object()))


def continue_one_chapter(project, *, target_chinese_chars=None, **kwargs):
    return _secure_continue_one_chapter(_prepared(project, target_chinese_chars=target_chinese_chars), **kwargs)


def promote_passing_draft(project, **_kwargs):
    return _secure_promote_passing_draft(_prepared(project))


class FakeClient:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0
        self.messages = []

    def complete(self, messages, *, temperature: float, max_tokens: int):
        self.calls += 1
        self.messages = messages
        return self.text


def _project(tmp_path):
    project = tmp_path / "文明升阶"
    (project / "production/final_chapters").mkdir(parents=True)
    (project / ".creative_os/import").mkdir(parents=True)
    (project / ".creative_os/knowledge").mkdir(parents=True)
    (project / "production/final_chapters/chapter_001.md").write_text("# 第1章\n前一章结尾。", encoding="utf-8")
    (project / ".creative_os/import/baseline.json").write_text(
        json.dumps(
            {"world_rules": [], "characters": [], "plot_milestones": [], "hooks": [], "style_constraints": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project / ".creative_os/import/conflicts.json").write_text("[]", encoding="utf-8")
    (project / ".creative_os/import/approval.json").write_text('{"resolutions": {}}', encoding="utf-8")
    return project


def test_dry_run_compiles_context_without_calling_model(tmp_path):
    client = FakeClient("unused")

    result = continue_one_chapter(_project(tmp_path), client=client, dry_run=True)

    assert client.calls == 0
    assert result.context_path.exists()
    assert result.status == "dry_run"


def test_failed_review_does_not_promote_chapter_or_memory(tmp_path):
    project = _project(tmp_path)

    result = continue_one_chapter(project, client=FakeClient("# 第2章\n太短。"), max_attempts=1)

    assert result.status == "fail"
    assert result.draft_path.exists()
    assert not (project / "production/final_chapters/chapter_002.md").exists()


def test_passing_draft_can_be_promoted_after_revalidation(tmp_path):
    project = _project(tmp_path)
    draft = project / ".creative_os/llm_writer/drafts/chapter_002.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# 第2章\n" + "正文" * 3000, encoding="utf-8")

    result = promote_passing_draft(project)

    assert result.status == "pass"
    assert result.final_chapter_path.exists()
    review = json.loads((project / ".creative_os/reviews/chapter_002_continuation.json").read_text(encoding="utf-8"))
    assert review["issues"] == []
    assert all(item.status == "candidate" for item in result.experiences)


def test_failed_retries_record_total_elapsed_time(tmp_path, monkeypatch):
    project = _project(tmp_path)
    moments = iter([10.0, 11.5, 12.0, 14.5])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(moments))

    continue_one_chapter(project, client=FakeClient("# 第2章\n太短。"), max_attempts=2)

    status = json.loads((project / "production/runs/status/chapter_002_status.json").read_text(encoding="utf-8"))
    assert status["elapsed_seconds"] == 4.0


def test_writer_receives_compiled_knowledge_and_previous_chapter_ending(tmp_path):
    project = _project(tmp_path)
    baseline_path = project / ".creative_os/import/baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline["plot_milestones"] = [
        {
            "title": "当前大纲",
            "content": "| 2 | 两张脸 | 与父母摊牌 | 2000 |",
            "source_path": "02_Plot/Plot_Outline.md",
        }
    ]
    baseline_path.write_text(json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
    client = FakeClient("# 第2章：两张脸\n" + "正文" * 3000)

    continue_one_chapter(project, client=client, max_attempts=1)

    assert (project / ".creative_os/memory/items/chapter-002-summary.json").exists()

    prompt = client.messages[-1].content
    assert "前一章结尾" in prompt
    assert "第 2 章《两张脸》：与父母摊牌" in prompt
    assert "02_Plot/Plot_Outline.md" in prompt
    assert "| 2 | 两张脸 | 与父母摊牌 | 2000 |" in prompt
    assert "首行必须使用一级标题" in prompt
    assert "目标中文字符数：约 2000" in prompt


def test_runner_accepts_timed_completion_from_openai_compatible_client(tmp_path):
    class TimedClient(FakeClient):
        def complete(self, messages, *, temperature: float, max_tokens: int):
            super().complete(messages, temperature=temperature, max_tokens=max_tokens)
            return TimedCompletion(content="# 第2章\n" + "正文" * 1200, elapsed_seconds=2.5, usage=None)

    project = _project(tmp_path)
    result = continue_one_chapter(project, client=TimedClient(""), max_attempts=1)

    assert result.draft_path is not None
    status = json.loads((project / "production/runs/status/chapter_002_status.json").read_text(encoding="utf-8"))
    assert status["elapsed_seconds"] == 2.5


def test_retry_includes_previous_quality_issues_in_writer_prompt(tmp_path):
    project = _project(tmp_path)
    client = FakeClient("# 第2章\n太短。")

    continue_one_chapter(project, client=client, max_attempts=2)

    assert "正文尚差篇幅" in client.messages[-1].content
    assert "只输出可直接接在末段后的正文" in client.messages[-1].content


def test_length_failure_uses_a_seamless_extension_instead_of_rewriting_the_draft(tmp_path):
    project = _project(tmp_path)

    class ExtendingClient(FakeClient):
        def complete(self, messages, *, temperature: float, max_tokens: int):
            self.calls += 1
            self.messages = messages
            return "# 第2章\n" + "初稿" * 600 if self.calls == 1 else "延续" * 800

    result = continue_one_chapter(project, client=ExtendingClient(""), max_attempts=2, target_chinese_chars=2000)

    assert result.status == "pass"
    text = result.final_chapter_path.read_text(encoding="utf-8")
    assert "初稿" in text and "延续" in text
    assert text.count("# 第2章") == 1


def test_length_failure_with_narrative_issue_still_extends_current_draft(tmp_path, monkeypatch):
    """防止混合错误分支丢弃长篇初稿并整章重写。"""
    project = _project(tmp_path)
    reviews = iter([
        ["below_minimum_chinese_chars", "narrative:supporting_agency_not_dramatized"],
        [],
    ])
    monkeypatch.setattr(runner, "_review", lambda *_args: next(reviews))

    class RepairingClient(FakeClient):
        def complete(self, messages, *, temperature: float, max_tokens: int):
            self.calls += 1
            self.messages = messages
            return "# 第2章\n" + "初稿" * 600 if self.calls == 1 else "配角继续行动" * 800

    client = RepairingClient("")
    result = continue_one_chapter(project, client=client, max_attempts=2, target_chinese_chars=2000)

    assert result.status == "pass"
    text = result.final_chapter_path.read_text(encoding="utf-8")
    assert "初稿" in text and "配角继续行动" in text
    assert "supporting_agency_not_dramatized" in client.messages[-1].content


def test_failed_length_draft_is_resumed_without_regenerating_opening(tmp_path, monkeypatch):
    """防止进程重启后丢弃已保存的长章草稿。"""
    project = _project(tmp_path)
    draft = project / ".creative_os/llm_writer/drafts/chapter_002.md"
    draft.parent.mkdir(parents=True)
    draft.write_text("# 第2章\n" + "已保存正文" * 500, encoding="utf-8")
    prepared = _prepared(project, target_chinese_chars=3000)
    review = project / ".creative_os/reviews/chapter_002_continuation.json"
    review.parent.mkdir(parents=True)
    review.write_text(json.dumps({
        "context": prepared.context.fingerprint,
        "issues": ["below_minimum_chinese_chars", "narrative:supporting_agency_not_dramatized"],
    }), encoding="utf-8")
    reviews = iter([[]])
    monkeypatch.setattr(runner, "_review", lambda *_args: next(reviews))
    client = FakeClient("配角完成独立选择" * 800)

    result = _secure_continue_one_chapter(prepared, client=client, max_attempts=1)

    assert result.status == "pass"
    text = result.final_chapter_path.read_text(encoding="utf-8")
    assert "已保存正文" in text and "配角完成独立选择" in text
    assert client.calls == 1


def test_runner_returns_recoverable_failure_when_model_execution_fails(tmp_path):
    project = _project(tmp_path)

    class FailingClient:
        model = "deepseek-v4-pro"

        def complete(self, messages, *, temperature, max_tokens):
            raise RuntimeError("LLM request failed: HTTP 402 Insufficient Balance")

    result = continue_one_chapter(project, client=FailingClient(), max_attempts=2)

    assert result.status == "fail"
    assert result.issues == ["model_execution_failed"]
    assert result.final_chapter_path is None
    assert not (project / "production/final_chapters/chapter_002.md").exists()


def test_chapter_run_writes_business_events_to_append_only_log(tmp_path):
    project = _project(tmp_path)

    continue_one_chapter(project, client=FakeClient("# 第2章\n太短。"), max_attempts=1)

    events = [
        json.loads(line)
        for line in (project / ".creative_os/runtime/events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types[:3] == ["TaskCreated", "TaskStarted", "ContextBuilt"]
    assert "CapabilityCalled" in event_types
    assert "ResultGenerated" in event_types
    assert event_types[-2:] == ["ReviewFailed", "TaskFailed"]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))


def test_passing_chapter_completes_production_loop_and_records_events(tmp_path):
    project = _project(tmp_path)
    result = continue_one_chapter(project, client=FakeClient("# 第2章\n" + "正文" * 3000), max_attempts=1)

    assert result.status == "pass"
    assert result.final_chapter_path is not None and result.final_chapter_path.exists()
    assert (project / ".creative_os/memory/items/chapter-002-summary.json").exists()
    events = [
        json.loads(line)
        for line in (project / ".creative_os/runtime/events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_types = [event["event_type"] for event in events]
    assert event_types[-4:] == ["ReviewPassed", "KnowledgeUpdated", "StateChanged", "TaskCompleted"]
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
