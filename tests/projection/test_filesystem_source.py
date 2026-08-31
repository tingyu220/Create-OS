from __future__ import annotations

import json
from pathlib import Path

import pytest

from creative_os.projection.filesystem_source import FilesystemProjectSource, ProjectionSourceError


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _make_project(root: Path, project_id: str = "book-a") -> Path:
    _write_json(root / "project.json", {"id": project_id, "name": "测试小说", "domain": "novel"})
    return root


def test_source_uses_project_metadata_identity_instead_of_global_state(tmp_path: Path) -> None:
    """捕获用进程级“当前项目”或目录外数据替代显式项目身份的实现。"""
    project = _make_project(tmp_path / "directory-name", project_id="book-a")

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.project_id == "book-a"
    assert all(not reference.locator.startswith("/") for reference in facts.source_refs)


def test_source_reads_chapter_status_with_traceable_reference(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    _write_json(
        project / "production/runs/status/chapter_029_status.json",
        {"chapter": 29, "status": "fail", "attempts": 2, "elapsed_seconds": 8.5, "issues": ["timeline_conflict"]},
    )

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.chapter_statuses[0].chapter_number == 29
    assert facts.chapter_statuses[0].issues == ("timeline_conflict",)
    assert facts.chapter_statuses[0].source_ref.locator == "production/runs/status/chapter_029_status.json"


def test_event_head_uses_last_sequence_and_event_id(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    event_path = project / ".creative_os/runtime/events.jsonl"
    event_path.parent.mkdir(parents=True)
    events = [
        {
            "event_id": "event-1",
            "event_type": "TaskStarted",
            "occurred_at": "2026-09-01T00:00:00+00:00",
            "sequence": 1,
            "task_id": "chapter-029",
            "execution_id": None,
            "payload": {"chapter": 29},
        },
        {
            "event_id": "event-2",
            "event_type": "TaskFailed",
            "occurred_at": "2026-09-01T00:01:00+00:00",
            "sequence": 2,
            "task_id": "chapter-029",
            "execution_id": "execution-2",
            "payload": {"error": "gate_failed"},
        },
    ]
    event_path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")

    heads = FilesystemProjectSource(project).read_head()
    facts = FilesystemProjectSource(project).read_facts()

    runtime_head = next(head for head in heads if head.source_kind == "runtime_event_log")
    assert runtime_head.cursor == "2:event-2"
    assert [event.sequence for event in facts.execution_events] == [1, 2]
    assert facts.execution_events[1].payload_json == '{"error":"gate_failed"}'


def test_missing_optional_sources_are_diagnostics_not_confirmed_empty_facts(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.chapter_statuses == ()
    assert facts.execution_events == ()
    assert {item.code for item in facts.diagnostics} >= {
        "chapter_status_source_missing",
        "runtime_event_log_missing",
        "writer_validation_report_source_missing",
    }


def test_source_reads_writer_validation_as_review_gate_and_runtime_fact(tmp_path: Path) -> None:
    """捕获独立 Writer 项目被误判为完全没有质量和运行数据的实现。"""
    project = _make_project(tmp_path / "book")
    _write_json(
        project / "production/reports/real_writer_validation.json",
        {
            "mode": "live",
            "model": "test-model",
            "chapter_id": "chapter_001",
            "stage": "review_failed",
            "review_passed": False,
            "blocking_codes": ["timeline_conflict"],
            "elapsed_seconds": 12.5,
        },
    )

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.gate_results[0].gate_id == "novel-review:chapter_001"
    assert facts.gate_results[0].status == "failed"
    assert facts.quality_issues[0].code == "timeline_conflict"
    assert facts.quality_issues[0].blocking is True
    assert facts.runtime_reports[0].stage == "review_failed"
    assert facts.runtime_reports[0].source_ref.locator == "production/reports/real_writer_validation.json"


def test_invalid_project_metadata_fails_closed(tmp_path: Path) -> None:
    project = tmp_path / "book"
    _write_json(project / "project.json", {"name": "无身份项目"})

    with pytest.raises(ProjectionSourceError, match="project_id_missing"):
        FilesystemProjectSource(project).read_facts()
