from pathlib import Path
from tests.fakes.fake_chapter_writer import FakeChapterWriter
from creative_os.domains.chapter_production_owner_registry import production_owner_registry

def test_fake_writer_builds_each_chapter_on_demand_without_precomputed_runs(tmp_path: Path):
    writer=FakeChapterWriter(tmp_path)
    artifacts=[]
    for chapter in range(1,11):
        artifact=writer.prepare(chapter)
        artifacts.append(artifact)
        assert artifact.metadata["chapter"] == chapter
        assert "body" not in artifact.metadata
        writer.close_reopen_all()
    assert len(artifacts)==10
    assert writer.calls == 10
    assert writer.prepared_runs == []

def test_owner_registry_is_production_defined_and_reopened_each_chapter(tmp_path: Path):
    registry=production_owner_registry()
    assert "reader_engagement" in registry and "writer_execution_authority" in registry
    writer=FakeChapterWriter(tmp_path)
    for _ in range(10): writer.close_reopen_all()
    assert all(writer.reopen_counts[name]==10 for name in registry)
