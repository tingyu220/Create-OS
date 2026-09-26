from creative_os.agent_runtime import WriterAgentRuntime


def test_agent_runtime_uses_current_draft_version_before_saving(tmp_path):
    runtime = WriterAgentRuntime(tmp_path)
    runtime.store.save(79, "已有版本", actor="作者", expected_version=None)
    current = runtime.store.current(79)
    assert current is not None
    assert current[0].version == 1

