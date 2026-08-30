import ast
from pathlib import Path

from creative_os.domains.novel_continuation import _is_pov_strategy_memory
from creative_os.memory.model import MemoryEvidence, MemoryItem, MemoryKind, MemoryScope


def test_context_filter_rejects_pov_strategy_candidate_memory():
    item = MemoryItem.new_candidate(
        id="pov-strategy-027", kind=MemoryKind.PROJECT_DECISION, scope=MemoryScope.PROJECT,
        scope_id="project", title="候选", content="备选人物", tags={"pov_strategy_candidate"},
        evidence=(MemoryEvidence("test", "test"),),
    )
    assert _is_pov_strategy_memory(item)


def test_writer_runner_does_not_import_pov_strategy():
    path = Path("creative_os/novel_continuation_runner.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any("pov_strategy" in module for module in modules)
