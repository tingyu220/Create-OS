from pathlib import Path


def test_writer_shell_has_editor_preview_and_save_controls():
    root = Path(__file__).parents[1] / "creative_os" / "web"
    html = (root / "writer.html").read_text(encoding="utf-8")
    script = (root / "writer.js").read_text(encoding="utf-8")
    assert 'id="editor"' in html
    assert 'id="preview"' in html
    assert "save_writer_draft" in script
    assert "/api/writer/chapters/" in script

