from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Callable
from uuid import uuid4

from creative_os.llm_metrics import TimedCompletion
from creative_os.runtime.model import ModelAdapter, RuntimeRequest, RuntimeResult
from creative_os.runtime.records import ExecutionRecord


class RuntimeExecutionError(RuntimeError):
    def __init__(self, message: str, *, record: ExecutionRecord) -> None:
        super().__init__(message)
        self.record = record


class RuntimeRunner:
    def __init__(
        self,
        record_sink: Callable[[ExecutionRecord], None] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._record_sink = record_sink
        self._clock = clock or time.monotonic

    def execute(self, request: RuntimeRequest, adapter: ModelAdapter) -> RuntimeResult:
        request.validate()
        started = datetime.now(timezone.utc)
        started_clock = self._clock()
        execution_id = f"execution-{uuid4().hex}"
        try:
            completion = adapter.complete(
                list(request.messages),
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            elapsed = self._clock() - started_clock
            output = completion.content if isinstance(completion, TimedCompletion) else str(completion)
            usage = completion.usage if isinstance(completion, TimedCompletion) else None
            record = self._record(request, execution_id, started, elapsed, "succeeded", None)
            self._emit(record)
            reported_elapsed = completion.elapsed_seconds if isinstance(completion, TimedCompletion) else elapsed
            return RuntimeResult(output, elapsed, usage, record, reported_elapsed)
        except Exception as error:
            elapsed = self._clock() - started_clock
            record = self._record(request, execution_id, started, elapsed, "failed", str(error))
            self._emit(record)
            raise RuntimeExecutionError(str(error), record=record) from error

    def _record(
        self,
        request: RuntimeRequest,
        execution_id: str,
        started: datetime,
        elapsed: float,
        status: str,
        error: str | None,
    ) -> ExecutionRecord:
        finished = datetime.now(timezone.utc)
        return ExecutionRecord(
            execution_id=execution_id,
            task_id=request.task_id,
            context_id=request.context_id,
            capability=request.capability,
            domain=request.domain,
            model=request.model,
            input_refs=request.input_refs,
            output_ref=f"{execution_id}:output" if status == "succeeded" else None,
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            elapsed_seconds=round(elapsed, 6),
            error=error,
        )

    def _emit(self, record: ExecutionRecord) -> None:
        if self._record_sink is not None:
            self._record_sink(record)
