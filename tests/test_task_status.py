from creative_os.task_status import ChapterTaskStatus, load_chapter_statuses, write_chapter_status


def test_write_and_load_chapter_status(tmp_path):
    status = ChapterTaskStatus(chapter=7, status="pass", attempts=2, elapsed_seconds=12.5, issues=[])

    path = write_chapter_status(tmp_path, status)
    statuses = load_chapter_statuses(tmp_path)

    assert path.name == "chapter_007_status.json"
    assert statuses == [status]


def test_status_path_supports_production_root(tmp_path):
    production_root = tmp_path / "production"
    status = ChapterTaskStatus(chapter=8, status="fail", attempts=1, elapsed_seconds=3.0, issues=["time_word_opener"])

    path = write_chapter_status(production_root, status)

    assert path == production_root / "runs" / "status" / "chapter_008_status.json"
    assert load_chapter_statuses(production_root) == [status]


def test_load_chapter_statuses_sorts_by_chapter(tmp_path):
    write_chapter_status(tmp_path, ChapterTaskStatus(chapter=10, status="pass", attempts=1, elapsed_seconds=1.0, issues=[]))
    write_chapter_status(tmp_path, ChapterTaskStatus(chapter=2, status="fail", attempts=2, elapsed_seconds=2.0, issues=["x"]))

    statuses = load_chapter_statuses(tmp_path)

    assert [status.chapter for status in statuses] == [2, 10]


def test_load_chapter_statuses_falls_back_to_legacy_llm_writer_run(tmp_path):
    run_dir = tmp_path / "production" / "llm_writer_pilot" / "runs"
    run_dir.mkdir(parents=True)
    (run_dir / "llm_writer_pilot_run.json").write_text(
        """
{
  "chapter_results": {
    "chapter_032": [],
    "chapter_033": ["time_word_opener"]
  },
  "attempts": {
    "chapter_032": 1,
    "chapter_033": 2
  },
  "metrics": {
    "chapter_032": {"elapsed_seconds": 4.5},
    "chapter_033": {"elapsed_seconds": 8.0}
  }
}
""".strip(),
        encoding="utf-8",
    )

    statuses = load_chapter_statuses(tmp_path)

    assert statuses == [
        ChapterTaskStatus(chapter=32, status="pass", attempts=1, elapsed_seconds=4.5, issues=[]),
        ChapterTaskStatus(chapter=33, status="fail", attempts=2, elapsed_seconds=8.0, issues=["time_word_opener"]),
    ]


def test_load_chapter_statuses_falls_back_to_legacy_run_from_production_root(tmp_path):
    production_root = tmp_path / "production"
    run_dir = production_root / "llm_writer_pilot" / "runs"
    run_dir.mkdir(parents=True)
    (run_dir / "llm_writer_pilot_run.json").write_text(
        '{"chapter_results":{"chapter_036":[]},"attempts":{},"metrics":{}}',
        encoding="utf-8",
    )

    statuses = load_chapter_statuses(production_root)

    assert statuses == [ChapterTaskStatus(chapter=36, status="pass", attempts=0, elapsed_seconds=0.0, issues=[])]
