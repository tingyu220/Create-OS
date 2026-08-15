import json

from creative_os.batch_runner import load_completed_chapters, select_pending_chapters


def test_load_completed_chapters_reads_passed_chapters(tmp_path):
    run_path = tmp_path / "llm_writer_pilot_run.json"
    run_path.write_text(
        json.dumps(
            {
                "chapter_results": {
                    "chapter_007": [],
                    "chapter_008": ["missing_fact:测试"],
                    "chapter_009": [],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert load_completed_chapters(run_path) == {7, 9}


def test_load_completed_chapters_returns_empty_set_when_run_file_is_missing(tmp_path):
    assert load_completed_chapters(tmp_path / "missing.json") == set()


def test_select_pending_chapters_skips_completed_by_default():
    assert select_pending_chapters([7, 8, 9], {7, 9}) == [8]


def test_select_pending_chapters_force_runs_all():
    assert select_pending_chapters([7, 8, 9], {7, 9}, force=True) == [7, 8, 9]
