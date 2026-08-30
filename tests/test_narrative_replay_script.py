import hashlib
import json

from scripts.replay_narrative import run


def _seed_six_chapter_project(root):
    for chapter_number in range(1, 7):
        chapter_id = f"chapter_{chapter_number:03d}"
        chapter_path = root / "production" / "final_chapters" / f"{chapter_id}.md"
        chapter_path.parent.mkdir(parents=True, exist_ok=True)
        chapter_path.write_text(f"# 第 {chapter_number} 章\n\n章节正文 {chapter_number}。\n", encoding="utf-8")
        task_path = root / "production" / chapter_id / "tasks" / "scene.json"
        task_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(
            json.dumps(
                {
                    "scene_spec": {
                        "goal": "推进调查" if chapter_number < 3 else f"章节功能 {chapter_number}",
                        "outcome": f"章节结果 {chapter_number}",
                    }
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return root


def _hashes(directory):
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.glob("chapter_*.md"))
    }


def test_replay_script_writes_stable_reports_without_modifying_chapters(tmp_path):
    root = _seed_six_chapter_project(tmp_path)
    output_dir = root / "production" / "reports"
    before = _hashes(root / "production" / "final_chapters")

    result = run(root, 1, 6, output_dir)
    json_path = output_dir / "narrative_replay_001_006.json"
    markdown_path = output_dir / "narrative_replay_001_006.md"
    first_json = json_path.read_bytes()
    first_markdown = markdown_path.read_bytes()
    second_result = run(root, 1, 6, output_dir)

    assert result["chapter_count"] == 6
    assert result == second_result
    assert json_path.read_bytes() == first_json
    assert markdown_path.read_bytes() == first_markdown
    assert _hashes(root / "production" / "final_chapters") == before
    payload = json.loads(first_json)
    assert payload["chapters"][0]["contract"]["evidence"]
    assert payload["issue_count"] >= 1
