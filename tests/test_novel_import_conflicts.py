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


def test_conflict_detector_recognizes_rewritten_chapter_count_claims_in_outline():
    draft = NovelBaselineDraft(
        canon_chapters=[CanonChapter(1, "开端", "text", "04_Chapters/第1章.md", "a")],
        world_rules=[],
        characters=[],
        plot_milestones=[_artifact("02_Plot/Plot_Outline.md", "截止今日，已重写/新增16章。")],
        hooks=[],
        style_constraints=[],
        knowledge_candidates=[],
    )

    issues = detect_import_conflicts(draft)

    issue = next(issue for issue in issues if issue.code == "completed_chapter_count_conflict")
    assert issue.severity == "high"
    assert issue.values == ["1", "16"]
    assert issue.sources == ["02_Plot/Plot_Outline.md", "04_Chapters/第1章.md"]


def _artifact(path: str, content: str) -> BaselineArtifact:
    return BaselineArtifact("source", content, path, "hash", "heading")
