from creative_os.domains.novel_baseline import BaselineArtifact, CanonChapter, NovelBaselineDraft
from creative_os.domains.novel_conflicts import detect_import_conflicts


def test_conflict_detector_reports_volume_and_chapter_count_disagreement():
    draft = NovelBaselineDraft(
        canon_chapters=[
            CanonChapter(1, "开端", "text", "04_Chapters/第1章.md", "a"),
            CanonChapter(2, "发展", "text", "04_Chapters/第2章.md", "b"),
        ],
        world_rules=[_artifact("核心框架.md", "全书规划4卷。")],
        characters=[],
        plot_milestones=[_artifact("06_重构方案.md", "重构为5卷。")],
        hooks=[],
        style_constraints=[_artifact("Novel_README.md", "当前总章节数：6章")],
        knowledge_candidates=[],
    )

    issues = detect_import_conflicts(draft)

    assert {"volume_count_conflict", "completed_chapter_count_conflict"} <= {issue.code for issue in issues}
    assert all(issue.sources for issue in issues)
    assert all(issue.resolution_required for issue in issues)


def test_conflict_detector_reports_duplicate_chapter_number():
    chapter = CanonChapter(1, "开端", "text", "a.md", "a")
    draft = NovelBaselineDraft([chapter, chapter], [], [], [], [], [], [])

    issues = detect_import_conflicts(draft)

    assert any(issue.code == "duplicate_chapter_number" and issue.severity == "high" for issue in issues)


def _artifact(path: str, content: str) -> BaselineArtifact:
    return BaselineArtifact("source", content, path, "hash", "heading")
