import os
import subprocess
import sys
from pathlib import Path

from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope, MemoryStatus
from creative_os.memory.store import JsonMemoryStore


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "memory_review.py"


def test_cli_rejects_system_approval_and_keeps_candidate(tmp_path):
    memory_root = tmp_path / "memory"
    store = JsonMemoryStore(memory_root)
    store.add_candidate(
        MemoryItem.new_candidate(
            id="exp-001",
            kind=MemoryKind.EXPERIENCE,
            scope=MemoryScope.DOMAIN,
            scope_id="novel",
            title="规则",
            content="内容",
            evidence=[MemoryEvidence(source_type="review", source_id="review-1")],
        )
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--memory-root", str(memory_root), "approve", "exp-001", "--actor", "system"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    assert result.returncode != 0
    assert store.get("exp-001").status == MemoryStatus.CANDIDATE
