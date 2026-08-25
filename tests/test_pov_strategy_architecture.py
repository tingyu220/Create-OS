import ast
from pathlib import Path


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    result = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)
    return result


def test_planner_has_no_memory_writer_or_network_dependency():
    imports = imported_modules(Path("creative_os/domains/pov_strategy_planner.py"))
    assert imports.isdisjoint({"creative_os.memory.store", "creative_os.llm_writer", "urllib", "requests"})


def test_writer_modules_do_not_import_pov_strategy():
    for path in (Path("creative_os/novel_continuation_runner.py"), Path("creative_os/llm_writer.py")):
        assert not any("pov_strategy" in name for name in imported_modules(path))


def test_pov_strategy_modules_are_small_and_have_no_wildcard_imports():
    files = sorted(Path("creative_os").rglob("pov_strategy*.py"))
    assert files
    for path in files:
        assert len(path.read_text(encoding="utf-8").splitlines()) <= 300, path
        tree = ast.parse(path.read_text(encoding="utf-8"))
        assert not any(isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names) for node in ast.walk(tree)), path


def test_planner_does_not_create_memory_items():
    planner_files = sorted(Path("creative_os/domains").glob("pov_strategy_*.py"))
    assert not any("MemoryItem" in path.read_text(encoding="utf-8") for path in planner_files)
