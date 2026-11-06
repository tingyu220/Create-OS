"""隔离模型与项目，验证任务时间在等待、查询和恢复之间保持真实。"""

from datetime import datetime
from threading import Event

from creative_os.agent_runtime import WriterAgentRuntime
from creative_os.agent_conversation_store import AgentConversationStore


def test_waiting_job_keeps_start_and_stage_time_across_queries(tmp_path, monkeypatch):
    entered, release = Event(), Event()

    class DelayedClient:
        def complete(self, *args, **kwargs):
            entered.set()
            assert release.wait(5), "测试模型等待超时"
            return "只读分析结果"

    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: DelayedClient())
    runtime = WriterAgentRuntime(tmp_path, project_id="progress-test")
    try:
        queued = runtime.submit("只分析本章", 1)
        assert entered.wait(5)
        thinking = runtime.get(queued.job_id)
        assert thinking.status == "thinking"
        assert thinking.started_at == queued.updated_at
        assert datetime.fromisoformat(thinking.status_updated_at) >= datetime.fromisoformat(thinking.started_at)
        before = runtime.conversation(1)["jobs"][0]
        restored = AgentConversationStore(tmp_path, "progress-test").conversation(1)["jobs"][0]
        assert restored["started_at"] == before["started_at"]
        assert restored["status_updated_at"] == before["status_updated_at"]
        runtime._set(queued.job_id, actual_words=0)
        assert runtime.get(queued.job_id).status_updated_at == thinking.status_updated_at
    finally:
        release.set()
        runtime._pool.shutdown(wait=True)
    done = runtime.get(queued.job_id)
    assert done.status == "completed"
    assert done.started_at == queued.updated_at
    assert done.status_updated_at == done.updated_at
    restored_runtime = WriterAgentRuntime(tmp_path, project_id="progress-test")
    try:
        assert restored_runtime.get(done.job_id).started_at == done.started_at
    finally:
        restored_runtime._pool.shutdown(wait=True)


def test_legacy_jobs_without_time_are_not_backfilled_from_update(tmp_path, monkeypatch):
    runtime = WriterAgentRuntime(tmp_path, project_id="progress-test")
    monkeypatch.setattr(runtime._pool, "submit", lambda *args: None)
    queued = runtime.submit("历史分析", 1)
    runtime._set(queued.job_id, status="completed")
    session = runtime.conversations.read(1)
    session["jobs"][queued.job_id].pop("started_at", None)
    session["jobs"][queued.job_id].pop("status_updated_at", None)
    runtime.conversations.write(session)
    runtime._pool.shutdown(wait=True)
    restored = WriterAgentRuntime(tmp_path, project_id="progress-test")
    try:
        old = restored.get(queued.job_id)
        assert old.started_at == "" and old.status_updated_at == ""
        assert old.updated_at
    finally:
        restored._pool.shutdown(wait=True)
