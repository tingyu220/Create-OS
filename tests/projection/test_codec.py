from __future__ import annotations

import json
import hashlib

import pytest

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.codec import ProjectionCodecError, decode_project_snapshot, encode_project_snapshot
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.overview import OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import SourceHead, SourceRef
from creative_os.projection.quality import QualitySnapshot
from creative_os.projection.trace import TraceSnapshot, TraceEntrySnapshot
from creative_os.projection.narrative import CharacterSnapshot, StoryThreadSnapshot, TimelineEntrySnapshot
from creative_os.projection.provenance import Derivation


def _snapshot() -> ProjectSnapshot:
    reference = SourceRef("chapter_status", "chapter-001", "production/status/001.json", "a" * 64)
    chapter = ChapterSnapshot("chapter-001", 1, "第一章", ChapterStatus.PASSED, 1, 2.5, (reference,))
    return ProjectSnapshot.create(
        project_id="book-a",
        built_at="2026-09-01T00:00:00+00:00",
        source_heads=(SourceHead("chapter_statuses", "status", "1", "b" * 64),),
        overview=OverviewSnapshot("complete", ProjectRunStatus.PASSED, 1, 0, (reference,)),
        chapters=(chapter,),
        quality=QualitySnapshot((), (), (reference,)),
        trace=TraceSnapshot((), ()),
    )


def test_snapshot_codec_round_trips_and_is_deterministic() -> None:
    snapshot = _snapshot()

    first = encode_project_snapshot(snapshot)
    second = encode_project_snapshot(snapshot)

    assert first == second
    assert decode_project_snapshot(first) == snapshot

def test_snapshot_codec_round_trips_nonempty_trace_entry() -> None:
    snapshot = _snapshot()
    ref = snapshot.overview.source_refs[0]
    trace = TraceSnapshot((TraceEntrySnapshot("event", 1, "event-1", "TaskStarted", "2026-09-01T00:00:00+00:00", "task-1", None, "TaskStarted task=task-1", (ref,)),), (ref,))
    snapshot = ProjectSnapshot.create(project_id=snapshot.project_id, built_at=snapshot.built_at, source_heads=snapshot.source_heads, overview=snapshot.overview, chapters=snapshot.chapters, quality=snapshot.quality, trace=trace)
    assert decode_project_snapshot(encode_project_snapshot(snapshot)) == snapshot


def test_snapshot_payload_has_no_absolute_machine_path() -> None:
    payload = encode_project_snapshot(_snapshot())

    assert "D:\\" not in payload
    assert "C:\\" not in payload


def test_codec_rejects_unknown_schema_version() -> None:
    payload = json.loads(encode_project_snapshot(_snapshot()))
    payload["schema_version"] = 999

    with pytest.raises(ProjectionCodecError, match="project_snapshot_schema_unsupported"):
        decode_project_snapshot(json.dumps(payload))


def test_timeline_codec_round_trips_structured_projection_fields() -> None:
    snapshot = _snapshot()
    reference = snapshot.overview.source_refs[0]
    timeline = TimelineEntrySnapshot(
        "事件A", "chapter_only", "第1章内", "clear", "{\"precision\":\"chapter_only\"}",
        (reference,), Derivation("active-timeline-state", (reference,)),
    )
    snapshot = ProjectSnapshot.create(
        project_id=snapshot.project_id, built_at=snapshot.built_at, source_heads=snapshot.source_heads,
        overview=snapshot.overview, chapters=snapshot.chapters, quality=snapshot.quality, trace=snapshot.trace,
        timeline=(timeline,),
    )

    assert decode_project_snapshot(encode_project_snapshot(snapshot)).timeline == (timeline,)


def test_v2_codec_round_trips_all_narrative_projections() -> None:
    snapshot = _snapshot()
    reference = snapshot.overview.source_refs[0]
    derivation = Derivation("narrative-state", (reference,))
    snapshot = ProjectSnapshot.create(
        project_id=snapshot.project_id, built_at=snapshot.built_at, source_heads=snapshot.source_heads,
        overview=snapshot.overview, chapters=snapshot.chapters, quality=snapshot.quality, trace=snapshot.trace,
        characters=(CharacterSnapshot("林彻", "{\"role\":\"pov\"}", (reference,), derivation),),
        story_threads=(StoryThreadSnapshot("主线", "main", "open", "{}", (reference,), derivation, "待解决"),),
        timeline=(TimelineEntrySnapshot("事件A", "chapter_only", "第1章内", "clear", "{}", (reference,), derivation),),
    )

    payload = json.loads(encode_project_snapshot(snapshot))

    assert payload["schema_version"] == 2
    assert decode_project_snapshot(json.dumps(payload)) == snapshot


def test_v1_payload_migrates_missing_narrative_projections_to_v2() -> None:
    current = json.loads(encode_project_snapshot(_snapshot()))
    for key in ("characters", "story_threads", "timeline"):
        current.pop(key)
    current["schema_version"] = 1
    identity = {key: current[key] for key in (
        "schema_version", "project_id", "source_heads", "overview", "chapters", "quality", "trace", "diagnostics",
    )}
    current["snapshot_id"] = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    snapshot = decode_project_snapshot(json.dumps(current))

    assert snapshot.schema_version == 2
    assert snapshot.characters == ()
    assert snapshot.story_threads == ()
    assert snapshot.timeline == ()
    assert json.loads(encode_project_snapshot(snapshot))["schema_version"] == 2


@pytest.mark.parametrize("schema_version", [1, 2])
def test_codec_rejects_tampered_snapshot_id(schema_version: int) -> None:
    payload = json.loads(encode_project_snapshot(_snapshot()))
    if schema_version == 1:
        for key in ("characters", "story_threads", "timeline"):
            payload.pop(key)
        identity = {key: payload[key] for key in (
            "schema_version", "project_id", "source_heads", "overview", "chapters", "quality", "trace", "diagnostics",
        )}
        payload["schema_version"] = 1
        identity["schema_version"] = 1
        payload["snapshot_id"] = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    payload["snapshot_id"] = "0" * 64

    with pytest.raises(ProjectionCodecError, match="project_snapshot_id_mismatch"):
        decode_project_snapshot(json.dumps(payload))


def test_codec_rejects_boolean_schema_version() -> None:
    payload = json.loads(encode_project_snapshot(_snapshot()))
    payload["schema_version"] = True

    with pytest.raises(ProjectionCodecError, match="project_snapshot_schema_unsupported"):
        decode_project_snapshot(json.dumps(payload))


def test_timeline_codec_round_trips_conflict_safe_fields() -> None:
    snapshot = _snapshot()
    reference = snapshot.overview.source_refs[0]
    timeline = TimelineEntrySnapshot(
        "事件A", "unknown", "unknown", "conflicted",
        '{"conflict_status":"conflicted","precision":"unknown","relative_order":"unknown"}',
        (reference,), Derivation("active-timeline-state", (reference,)),
    )
    snapshot = ProjectSnapshot.create(
        project_id=snapshot.project_id, built_at=snapshot.built_at, source_heads=snapshot.source_heads,
        overview=snapshot.overview, chapters=snapshot.chapters, quality=snapshot.quality, trace=snapshot.trace,
        timeline=(timeline,),
    )

    assert decode_project_snapshot(encode_project_snapshot(snapshot)).timeline == (timeline,)
