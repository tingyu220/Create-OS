"""最近位置只有显式记录才写入，损坏和非法位置不覆盖。"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import pytest
from creative_os.workspace_recent_store import WorkspaceRecentStore
from test_project_catalog import book, snapshot


def test_empty_read_does_not_create_files(tmp_path):
    assert WorkspaceRecentStore(tmp_path).read() == []
    assert list(tmp_path.iterdir()) == []


def test_record_concurrently_preserves_other_books_and_position(tmp_path):
    book(tmp_path, "甲书"); book(tmp_path, "乙书")
    store = WorkspaceRecentStore(tmp_path)
    before_projects = {name: snapshot(tmp_path / name) for name in ("甲书", "乙书")}
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda name: store.record(name, "writer", 3, source="draft"), ["甲书", "乙书"]))
    assert {row["project_id"] for row in store.read()} == {"甲书", "乙书"}
    updated = store.record("甲书", "story", None)
    assert updated["page"] == "story" and updated["chapter_number"] is None
    assert datetime.fromisoformat(updated["opened_at"]).utcoffset().total_seconds() == 0
    assert {name: snapshot(tmp_path / name) for name in before_projects} == before_projects
    restored = WorkspaceRecentStore(tmp_path).read()
    assert len(restored) == 2 and restored[0]["project_id"] == "甲书"


@pytest.mark.parametrize("project,page,chapter,source", [("../outside", "story", None, "auto"), ("missing", "writer", 1, "auto"),
    ("甲书", "other", None, "auto"), ("甲书", "writer", True, "auto"), ("甲书", "writer", 0, "auto"),
    ("甲书", "story", 1, "auto"), ("甲书", "writer", 1, "candidate")])
def test_invalid_location_has_no_side_effect(tmp_path, project, page, chapter, source):
    book(tmp_path, "甲书")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError):
        WorkspaceRecentStore(tmp_path).record(project, page, chapter, source=source)
    assert snapshot(tmp_path) == before


def test_corrupt_recent_is_reported_and_never_overwritten(tmp_path):
    book(tmp_path, "甲书")
    store = WorkspaceRecentStore(tmp_path)
    store.path.parent.mkdir(parents=True, exist_ok=True); store.path.write_text("{bad", encoding="utf-8")
    before = snapshot(tmp_path)
    with pytest.raises(ValueError, match="workspace_recent_corrupt"):
        store.read()
    with pytest.raises(ValueError, match="workspace_recent_corrupt"):
        store.record("甲书", "writer", 1)
    assert snapshot(tmp_path) == before


def test_recent_record_validates_payload_from_disk(tmp_path):
    book(tmp_path, "甲书")
    store = WorkspaceRecentStore(tmp_path); store.record("甲书", "writer", 2)
    data = json.loads(store.path.read_text(encoding="utf-8")); data["records"]["甲书"]["page"] = "../outside"
    store.path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="workspace_recent_corrupt"):
        store.read()
