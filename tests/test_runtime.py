import pytest

from creative_os.llm_metrics import TimedCompletion
from creative_os.runtime import ModelMessage, RuntimeExecutionError, RuntimeRequest, RuntimeRunner


def _request() -> RuntimeRequest:
    return RuntimeRequest(
        task_id="task-1",
        context_id="context-1",
        capability="writing",
        domain="novel",
        model="test-model",
        messages=(ModelMessage("user", "写一段正文"),),
        input_refs=(("chapter", "chapter-1"),),
        max_tokens=100,
    )


class FakeAdapter:
    model = "test-model"

    def complete(self, messages, *, temperature, max_tokens):
        return TimedCompletion("正文", 0.25, None)


def test_runtime_executes_adapter_and_emits_auditable_record():
    records = []
    clock = iter([10.0, 11.25])

    result = RuntimeRunner(records.append, clock=lambda: next(clock)).execute(_request(), FakeAdapter())

    assert result.output == "正文"
    assert result.elapsed_seconds == 1.25
    assert result.reported_elapsed_seconds == 0.25
    assert result.record.status == "succeeded"
    assert result.record.task_id == "task-1"
    assert result.record.context_id == "context-1"
    assert result.record.model == "test-model"
    assert records == [result.record]


def test_runtime_converts_adapter_failure_to_runtime_error_and_records_failure():
    records = []

    class FailingAdapter:
        def complete(self, messages, *, temperature, max_tokens):
            raise ValueError("provider unavailable")

    with pytest.raises(RuntimeExecutionError) as error:
        RuntimeRunner(records.append, clock=iter([1.0, 1.5]).__next__).execute(_request(), FailingAdapter())

    assert error.value.record.status == "failed"
    assert error.value.record.error == "provider unavailable"
    assert records[0] == error.value.record


def test_runtime_rejects_invalid_request_before_calling_adapter():
    request = _request()
    invalid = RuntimeRequest(
        task_id=request.task_id,
        context_id=request.context_id,
        capability=request.capability,
        domain=request.domain,
        model=request.model,
        messages=(),
    )

    with pytest.raises(ValueError, match="messages"):
        RuntimeRunner().execute(invalid, FakeAdapter())
