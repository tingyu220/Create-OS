from creative_os.agent_runtime import WriterAgentRuntime


def test_agent_runtime_submits_a_queued_job(tmp_path):
    job = WriterAgentRuntime(tmp_path).submit("继续写这一章", 79)
    assert job.status == "queued"
    assert job.job_id.startswith("agent-")
    assert job.updated_at
