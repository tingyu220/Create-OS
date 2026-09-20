from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from creative_os.projection.filesystem_source import FilesystemProjectSource, ProjectionSourceError
from creative_os.domains.reader_engagement_store import ReaderEngagementStore
from creative_os.domains.chapter_run_checkpoint import ChapterRunCheckpoint, ChapterRunState
from creative_os.domains.chapter_run_checkpoint_store import ChapterRunCheckpointStore


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _make_project(root: Path, project_id: str = "book-a") -> Path:
    _write_json(root / "project.json", {"id": project_id, "name": "测试小说", "domain": "novel"})
    return root


def test_source_reads_chapter_checkpoint_chain(tmp_path: Path) -> None:
    project = _make_project(tmp_path)
    store = ChapterRunCheckpointStore(project)
    initial = ChapterRunCheckpoint.initial("book-a", 7)
    store.append(initial)
    store.append(initial.advance(ChapterRunState.READINESS_APPROVED, ("readiness",)))

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.chapter_checkpoints[-1].state == "readiness_approved"
    assert facts.chapter_checkpoints[-1].chapter_number == 7
    assert any(item.source_kind == "chapter_checkpoint" for item in facts.source_refs)


def _rewrite_engagement_record(project: Path, record_type: str, mutate) -> None:
    records_path = project / ".creative_os/engagement/records.jsonl"
    envelopes = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    for envelope in envelopes:
        if envelope["record"]["record_type"] == record_type:
            mutate(envelope["record"])
    previous_hash = "0" * 64
    for sequence, envelope in enumerate(envelopes, start=1):
        envelope["sequence"] = sequence
        envelope["previous_hash"] = previous_hash
        base = {key: value for key, value in envelope.items() if key != "entry_hash"}
        envelope["entry_hash"] = hashlib.sha256(
            json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        previous_hash = envelope["entry_hash"]
    records_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n" for item in envelopes),
        encoding="utf-8",
    )
    (project / ".creative_os/engagement/head.json").write_text(
        json.dumps({"count": len(envelopes), "head_hash": previous_hash}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def _materialized_expectation(project: Path):
    store = ReaderEngagementStore(project)
    candidate = store.append_expectation_candidate({
        "expectation_id": "expectation-1",
        "from_state": "absent",
        "to_state": "open",
        "content_hash": "a" * 64,
        "evidence": [{"kind": "intent", "value": "promise"}],
    })
    transition = store.materialize_transition(
        candidate.record_id,
        {"actor": "editor", "reason": "reviewed", "disposition": "approved"},
        json.loads(store.head_path.read_text(encoding="utf-8"))["head_hash"],
    )
    return candidate, transition


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


def test_source_excludes_state_snapshot_whose_memory_is_still_candidate(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    _write_json(
        project / ".creative_os/memory/items/state-chapter-001-character.json",
        {"id": "state-chapter-001-character", "status": "candidate"},
    )
    _write_json(
        project / ".creative_os/state/snapshots/character/林子轩.json",
        {
            "schema_version": 2,
            "kind": "character",
            "subject": "林子轩",
            "fields": {"current_goal": "候选内容"},
            "latest_change": "state-chapter-001-character",
        },
    )

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.active_states == ()


def test_read_facts_validates_engagement_without_creating_authority_lock(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    records_path = project / ".creative_os/engagement/records.jsonl"
    records_path.parent.mkdir(parents=True)
    records_path.write_text("not-json\n", encoding="utf-8")

    facts = FilesystemProjectSource(project).read_facts()

    assert any(item.code == "engagement_authority_chain_invalid" for item in facts.diagnostics)
    assert not (project / ".creative_os/memory").exists()


def test_read_head_tracks_memory_item_status_changes(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    memory_path = project / ".creative_os/memory/items/state-hook-001.json"
    _write_json(memory_path, {"id": "state-hook-001", "status": "active"})

    source = FilesystemProjectSource(project)
    before = source.read_head()
    _write_json(memory_path, {"id": "state-hook-001", "status": "archived"})

    after = source.read_head()

    assert before != after


def test_source_diagnoses_unproven_open_loop_without_inventing_one(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    _write_json(
        project / ".creative_os/memory/items/state-hook-001.json",
        {"id": "state-hook-001", "status": "active"},
    )
    _write_json(
        project / ".creative_os/state/snapshots/hook/钥匙线.json",
        {
            "schema_version": 2,
            "kind": "hook",
            "subject": "钥匙线",
            "fields": {"status": "open"},
            "latest_change": "state-hook-001",
        },
    )

    facts = FilesystemProjectSource(project).read_facts()

    assert json.loads(facts.active_states[0].fields_json) == {"status": "open"}
    assert any(item.code == "story_thread_open_loop_unproven" for item in facts.diagnostics)


def test_source_projects_only_approved_expectation_transition(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    store = ReaderEngagementStore(project)
    candidate = store.append_expectation_candidate({
        "expectation_id": "expectation-1",
        "from_state": "absent",
        "to_state": "open",
        "content_hash": "a" * 64,
        "evidence": [{"kind": "intent", "value": "promise"}],
    })
    transition = store.materialize_transition(
        candidate.record_id,
        {"actor": "editor", "reason": "reviewed", "disposition": "approved"},
        json.loads(store.head_path.read_text(encoding="utf-8"))["head_hash"],
    )

    facts = FilesystemProjectSource(project).read_facts()

    assert len(facts.engagement_expectations) == 1
    fact = facts.engagement_expectations[0]
    assert fact.expectation_id == "expectation-1"
    assert fact.source_ref.source_id == transition.record_id
    assert fact.decision_source_ref.source_id == candidate.record_id
    assert not any(item.code == "engagement_authority_incomplete" for item in facts.diagnostics)


@pytest.mark.parametrize(
    ("record_type", "mutation"),
    [
        ("expectation_decision", lambda record: record["payload"].update({"candidate_id": "other-candidate"})),
        ("expectation_decision", lambda record: record["payload"].update({"decision_hash": "f" * 64})),
        ("expectation_decision", lambda record: record["payload"].update({"actor": ""})),
        ("expectation_decision", lambda record: record["payload"].update({"reason": ""})),
        ("expectation_decision", lambda record: record["payload"].update({"disposition": "rejected"})),
        ("expectation_decision", lambda record: record.update({"record_id": "other-decision"})),
        ("expectation_transition", lambda record: record.update({"record_id": "other-transition"})),
        ("expectation_transition", lambda record: record["payload"].update({"candidate": {"expectation_id": "other"}})),
        ("expectation_transition", lambda record: record["payload"].update({"decision_hash": "f" * 64})),
        ("expectation_transition", lambda record: record.update({"content_hash": "b" * 64})),
    ],
)
def test_source_rejects_cryptographically_valid_but_semantically_unbound_expectation_chain(
    tmp_path: Path, record_type: str, mutation,
) -> None:
    project = _make_project(tmp_path / "book")
    _materialized_expectation(project)
    _rewrite_engagement_record(project, record_type, mutation)

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.engagement_expectations == ()
    assert any(item.code == "engagement_authority_incomplete" for item in facts.diagnostics)


def test_engagement_authority_head_tracks_records_file(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    store = ReaderEngagementStore(project)
    store.append_expectation_candidate({
        "expectation_id": "expectation-1",
        "from_state": "absent",
        "to_state": "open",
        "content_hash": "a" * 64,
        "evidence": [{"kind": "intent", "value": "promise"}],
    })

    head = next(item for item in FilesystemProjectSource(project).read_head() if item.source_kind == "engagement_authority")

    assert head.source_id == "records"
    assert head.content_hash
    assert head.cursor is None


def test_source_keeps_candidate_or_incomplete_engagement_chain_empty(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "book")
    ReaderEngagementStore(project).append_expectation_candidate({
        "expectation_id": "expectation-1",
        "from_state": "absent",
        "to_state": "open",
        "content_hash": "a" * 64,
        "evidence": [{"kind": "intent", "value": "promise"}],
    })

    facts = FilesystemProjectSource(project).read_facts()

    assert facts.engagement_expectations == ()
    assert any(item.code == "engagement_authority_incomplete" for item in facts.diagnostics)
