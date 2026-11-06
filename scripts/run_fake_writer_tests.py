"""运行 Writer/故事回归，默认拒绝真实模型客户端及 urllib 外网出口。"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import pytest
    from scripts.fake_validation_guard import fake_validation_guard
    tests = sys.argv[1:] or [str(path.relative_to(ROOT)) for path in sorted((ROOT / "tests").glob("test_*.py"))
                            if path.name.startswith(("test_writer_", "test_agent_", "test_story_")) or path.stem in {"test_web_workspace", "test_web_workspace_routes", "test_web_command_dto", "test_novel_project", "test_fake_validation_guard"}]
    with fake_validation_guard():
        return pytest.main([*tests, "-q", "--tb=short"])


if __name__ == "__main__":
    raise SystemExit(main())
