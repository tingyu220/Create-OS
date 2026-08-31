from __future__ import annotations

import json

import pytest

from creative_os.projection.chapters import ChapterSnapshot, ChapterStatus
from creative_os.projection.codec import ProjectionCodecError, decode_project_snapshot, encode_project_snapshot
from creative_os.projection.model import ProjectSnapshot
from creative_os.projection.overview import OverviewSnapshot, ProjectRunStatus
from creative_os.projection.provenance import SourceHead, SourceRef
from creative_os.projection.quality import QualitySnapshot
from creative_os.projection.trace import TraceSnapshot


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


def test_snapshot_payload_has_no_absolute_machine_path() -> None:
    payload = encode_project_snapshot(_snapshot())

    assert "D:\\" not in payload
    assert "C:\\" not in payload


def test_codec_rejects_unknown_schema_version() -> None:
    payload = json.loads(encode_project_snapshot(_snapshot()))
    payload["schema_version"] = 999

    with pytest.raises(ProjectionCodecError, match="project_snapshot_schema_unsupported"):
        decode_project_snapshot(json.dumps(payload))
