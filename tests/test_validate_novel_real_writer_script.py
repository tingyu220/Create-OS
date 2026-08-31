import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "projects" / "novel_domain_validation" / "validation" / "independent_short_story.json"
SCRIPT = ROOT / "scripts" / "validate_novel_real_writer.py"


def _subprocess_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR"}}


def test_fake_cli_writes_atomic_redacted_report_without_environment_file(tmp_path):
    report = tmp_path / "nested" / "writer-report.json"
    missing_env = tmp_path / "missing.env"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture", str(FIXTURE), "--mode", "fake", "--report", str(report), "--env-file", str(missing_env)],
        cwd=ROOT,
        env=_subprocess_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["stage"] == "compile_candidate_ready"
    assert payload["review_passed"] is True
    assert payload["provider_kind"] == "fake"
    assert "api_key" not in payload
    assert "authorization" not in payload
    assert list(report.parent.glob(".writer-report.json.*.tmp")) == []


def test_live_cli_returns_configuration_exit_code_without_credentials(tmp_path):
    report = tmp_path / "live-report.json"

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--fixture", str(FIXTURE), "--mode", "live", "--report", str(report), "--env-file", str(tmp_path / "missing.env")],
        cwd=ROOT,
        env=_subprocess_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "live_writer_configuration_missing" in completed.stderr
    assert not report.exists()
