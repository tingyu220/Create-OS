import json

import creative_os.novel_continuation_runner as runner
from creative_os.llm_metrics import TimedCompletion
from creative_os.novel_continuation_runner import continue_one_chapter, promote_passing_draft


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

    assert "上一版未通过" in client.messages[-1].content
    assert "below_minimum_chinese_chars" in client.messages[-1].content
