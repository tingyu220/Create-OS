from pathlib import Path
import subprocess, sys
from creative_os.domains.chapter_production_owner_registry import validate_production_exit_manifest

def test_exit_manifest_matches_real_symbols():
    assert validate_production_exit_manifest() == ()

def test_legacy_writer_cli_direct_entry_is_disabled():
    script=Path('scripts/run_llm_writer_pilot.py')
    result=subprocess.run([sys.executable,str(script),'--project-root','x','--chapters','1'],capture_output=True,text=True)
    assert result.returncode != 0
    assert 'direct Writer entry is disabled' in result.stderr
