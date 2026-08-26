import subprocess
import sys


def test_inspect_script_exposes_no_write_mode():
    result = subprocess.run([sys.executable, "scripts/inspect_pov_strategy.py", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "--no-write" in result.stdout
