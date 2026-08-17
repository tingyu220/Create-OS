import json

import creative_os.novel_continuation_runner as runner
from creative_os.novel_continuation_runner import continue_one_chapter


class FakeClient:
    def __init__(self, text: str):
        self.text = text
        self.calls = 0

    def complete(self, messages, *, temperature: float, max_tokens: int):
        self.calls += 1
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
    assert all(item.status == "candidate" for item in result.experiences)


def test_failed_retries_record_total_elapsed_time(tmp_path, monkeypatch):
    project = _project(tmp_path)
    moments = iter([10.0, 11.5, 12.0, 14.5])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(moments))

    continue_one_chapter(project, client=FakeClient("# 第2章\n太短。"), max_attempts=2)

    status = json.loads((project / "production/runs/status/chapter_002_status.json").read_text(encoding="utf-8"))
    assert status["elapsed_seconds"] == 4.0
