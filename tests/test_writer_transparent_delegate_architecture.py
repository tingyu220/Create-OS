"""透明委派的静态反例及真实 Writer/Runner 调用链验证，全部隔离。"""

import ast
from pathlib import Path
import time
from functools import lru_cache

import pytest

from writer_architecture_checks import qualified_definitions, signature, validate_transparent_delegate


@lru_cache(maxsize=1)
def _production_sources():
    return {path.as_posix(): path.read_text(encoding="utf-8") for path in Path("creative_os").rglob("*.py")}


def sources():
    return _production_sources().copy()


def append_to_writer(actual, code):
    tree = ast.parse(actual["creative_os/agent_runtime.py"])
    qualified_definitions(tree)["WriterAgentRuntime._run"].body.extend(ast.parse(code).body)
    actual["creative_os/agent_runtime.py"] = ast.unparse(tree)


def test_delegate_contract_accepts_production_and_import_aliases():
    actual = sources()
    validate_transparent_delegate(actual)
    actual = sources()
    actual["creative_os/agent_runtime.py"] = actual["creative_os/agent_runtime.py"].replace(
        "ContextCapture, CapturingModelAdapter, WriterContextSourceQuery", "ContextCapture, WriterContextSourceQuery"
    ).replace("from creative_os.runtime.runner import RuntimeRunner", "from creative_os.runtime.runner import RuntimeRunner as RunnerAlias\nimport creative_os.writer_context_sources as delegate_module").replace(
        "CapturingModelAdapter(client,", "delegate_module.CapturingModelAdapter(client,"
    ).replace("RuntimeRunner().execute", "RunnerAlias().execute")
    validate_transparent_delegate(actual)
    actual = sources()
    actual["creative_os/agent_runtime.py"] = actual["creative_os/agent_runtime.py"].replace(
        "ContextCapture, CapturingModelAdapter,", "ContextCapture, CapturingModelAdapter as CaptureAlias,"
    ).replace("CapturingModelAdapter(client,", "CaptureAlias(client,")
    validate_transparent_delegate(actual)


def test_qualified_definitions_distinguish_classes_and_signature_includes_kwargs():
    tree = ast.parse("class Other:\n def complete(self, x): pass\nclass CapturingModelAdapter:\n def complete(self, messages, **kwargs): pass\n")
    nodes = qualified_definitions(tree)
    assert {"Other.complete", "CapturingModelAdapter.complete"} <= nodes.keys()
    assert signature("CapturingModelAdapter.complete", nodes["CapturingModelAdapter.complete"]) == "CapturingModelAdapter.complete(self,messages,**kwargs)"


@pytest.mark.parametrize("bad", [
    "from creative_os.writer_context_sources import CapturingModelAdapter\ndef bypass(c, s, m):\n return CapturingModelAdapter(c,s).complete(m)",
    "from creative_os.writer_context_sources import CapturingModelAdapter as C\ndef bypass(c,s,m):\n return C(c,s).complete(m)",
    "import creative_os.writer_context_sources as source\ndef bypass(c,s,m):\n return source.CapturingModelAdapter(c,s).complete(m)",
    "from creative_os.agent_runtime import CapturingModelAdapter as C\ndef bypass(c,s,m):\n return C(c,s).complete(m)",
    "from .writer_context_sources import CapturingModelAdapter as C\ndef bypass(c,s,m):\n return C(c,s).complete(m)",
    "from creative_os.writer_context_sources import CapturingModelAdapter as C\nAlias = C",
    "import creative_os.writer_context_sources as source\nAlias = source",
    "from creative_os.writer_context_sources import *",
    "from creative_os.writer_context_sources import CapturingModelAdapter as C\nfrom other import Other as C\ndef bypass(c,s,m):\n return C(c,s).complete(m)",
])
def test_business_direct_or_alias_paths_are_rejected(bad):
    actual = sources()
    actual["creative_os/other_business.py"] = bad
    with pytest.raises(AssertionError):
        validate_transparent_delegate(actual)


@pytest.mark.parametrize("code", [
    "import creative_os.agent_runtime as module\nproxy = module\ndef bypass(c,s,m):\n return proxy.CapturingModelAdapter(c,s).complete(m)",
    "from creative_os import agent_runtime as module\nconstructor = getattr(module, 'CapturingModelAdapter')",
])
def test_reexport_module_cannot_escape_to_assignment_or_lookup(code):
    actual = sources()
    actual["creative_os/other_business.py"] = code
    with pytest.raises(AssertionError, match="delegate module escaped"):
        validate_transparent_delegate(actual)


@pytest.mark.parametrize("replacement", [
    "other_entry(CapturingModelAdapter(client, callback))",
    "CapturingModelAdapter(client, callback).complete(messages)",
    "RuntimeRunner().execute(request, other_entry(CapturingModelAdapter(client, callback)))",
    "RuntimeRunner().execute(CapturingModelAdapter(client, callback), adapter)",
])
def test_only_immediate_runtime_adapter_argument_is_allowed(replacement):
    actual = sources()
    append_to_writer(actual, replacement)
    with pytest.raises(AssertionError, match="delegate not immediate adapter argument"):
        validate_transparent_delegate(actual)


def test_assignment_escape_even_inside_approved_method_is_rejected():
    actual = sources()
    append_to_writer(actual, "alias = CapturingModelAdapter\nbound = alias(client, callback).complete\nreturn bound(messages)")
    with pytest.raises(AssertionError, match="delegate class escaped"):
        validate_transparent_delegate(actual)


@pytest.mark.parametrize("owner", ["WriterAgentRuntime._execute_story_step", "WriterAgentRuntime.submit"])
def test_story_entry_still_rejects_adapter_loop_and_undeclared_construction(owner):
    actual = sources()
    tree = ast.parse(actual["creative_os/agent_runtime.py"])
    method = qualified_definitions(tree)[owner]
    method.body.extend(ast.parse("for item in messages:\n RuntimeRunner().execute(request, CapturingModelAdapter(client, callback))").body)
    actual["creative_os/agent_runtime.py"] = ast.unparse(tree)
    with pytest.raises(AssertionError, match="construction in loop"):
        validate_transparent_delegate(actual)


def test_runner_rebinding_and_business_loop_are_rejected():
    actual = sources()
    append_to_writer(actual, "RuntimeRunner = other_entry")
    with pytest.raises(AssertionError, match="import reassigned"):
        validate_transparent_delegate(actual)
    actual = sources()
    append_to_writer(actual, "for item in messages:\n RuntimeRunner().execute(request, CapturingModelAdapter(client, callback))")
    with pytest.raises(AssertionError, match="construction in loop"):
        validate_transparent_delegate(actual)
    actual = sources()
    append_to_writer(actual, "try:\n pass\nexcept Exception as RuntimeRunner:\n pass")
    with pytest.raises(AssertionError, match="shadowed by exception"):
        validate_transparent_delegate(actual)


@pytest.mark.parametrize("body", [
    "self.capture(messages)\nself.client.complete(messages, **kwargs)\nreturn self.client.complete(messages, **kwargs)",
    "messages.append('changed')\nself.capture(messages)\nreturn self.client.complete(messages, **kwargs)",
    "kwargs['temperature'] = 0\nself.capture(messages)\nreturn self.client.complete(messages, **kwargs)",
    "self.capture(messages)\nreturn self.client.complete(list(messages), **kwargs)",
    "self.capture(messages)\nreturn self.client.complete(messages, **dict(kwargs))",
    "for item in messages:\n self.capture(messages)\nreturn self.client.complete(messages, **kwargs)",
    "if messages:\n self.capture(messages)\nreturn self.client.complete(messages, **kwargs)",
    "return self.client.complete(messages, **kwargs)\nself.capture(messages)",
])
def test_wrapper_cannot_rewrite_repeat_loop_or_reorder(body):
    actual = sources()
    tree = ast.parse(actual["creative_os/writer_context_sources.py"])
    method = qualified_definitions(tree)["CapturingModelAdapter.complete"]
    method.body = ast.parse(body).body
    actual["creative_os/writer_context_sources.py"] = ast.unparse(tree)
    with pytest.raises(AssertionError):
        validate_transparent_delegate(actual)


def finish(runtime, job):
    for _ in range(300):
        current = runtime.get(job.job_id)
        if current.status in {"completed", "failed"}:
            return current
        time.sleep(0.01)
    raise AssertionError("隔离任务未结束")


@pytest.mark.parametrize("outcome", ["rejected", "success", "failure"])
def test_actual_writer_chain_validates_before_capture_and_preserves_runtime_records(tmp_path, monkeypatch, outcome):
    from creative_os.agent_runtime import WriterAgentRuntime
    from creative_os.runtime.model import RuntimeRequest
    from creative_os.runtime.runner import RuntimeRunner
    from creative_os.writer_context_sources import ContextCapture

    events, records, kwargs_seen = [], [], []
    original_validate, original_snapshot = RuntimeRequest.validate, ContextCapture.snapshot

    def validate(request):
        events.append("validate")
        if outcome == "rejected":
            raise ValueError("isolated_request_rejected")
        return original_validate(request)

    def snapshot(capture, *args, **kwargs):
        events.append("capture")
        return original_snapshot(capture, *args, **kwargs)

    class FakeClient:
        def complete(self, messages, **kwargs):
            events.append("client")
            kwargs_seen.append(kwargs)
            if outcome == "failure":
                raise RuntimeError("isolated_provider_failure")
            return "隔离候选正文"

    monkeypatch.setattr(RuntimeRequest, "validate", validate)
    monkeypatch.setattr(ContextCapture, "snapshot", snapshot)
    monkeypatch.setattr("creative_os.agent_runtime.OpenAICompatibleClient.from_env", lambda: FakeClient())
    monkeypatch.setattr("creative_os.agent_runtime.RuntimeRunner", lambda: RuntimeRunner(record_sink=records.append))
    runtime = WriterAgentRuntime(tmp_path, project_id="p")
    try:
        job = finish(runtime, runtime.submit("生成隔离候选", 1, mode="act"))
        if outcome == "rejected":
            assert events == ["validate"] and records == []
            assert job.context_snapshot is None and job.status == "failed"
        else:
            assert events == ["validate", "capture", "client"]
            assert kwargs_seen == [{"temperature": 0.78, "max_tokens": 12000}]
            assert len(records) == 1 and records[0].task_id == job.job_id
            assert records[0].status == ("succeeded" if outcome == "success" else "failed")
            if outcome == "failure":
                assert records[0].error == "isolated_provider_failure" and job.status == "failed"
            else:
                assert job.status == "completed"
        assert runtime.store.current(1) is None
    finally:
        runtime._pool.shutdown(wait=True)
