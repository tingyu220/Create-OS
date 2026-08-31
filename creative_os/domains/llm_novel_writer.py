from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from creative_os.domains.novel_writer import NovelDraft, NovelWritingError, NovelWritingRequest
from creative_os.domains.novel_writer_prompt import (
    DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
    build_novel_writer_messages,
)
from creative_os.domains.novel_writer_repair_prompt import build_novel_writer_repair_messages
from creative_os.llm_writer import ModelClient
from creative_os.runtime import ModelMessage, RuntimeExecutionError, RuntimeRequest, RuntimeResult, RuntimeRunner


@dataclass(frozen=True, slots=True)
class NovelWriterConfig:
    temperature: float = 0.7
    max_tokens: int = 6000
    minimum_reviewable_chars: int = 500
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION
    max_contract_repairs: int = 1

    def __post_init__(self) -> None:
        if self.max_contract_repairs not in (0, 1):
            raise ValueError("novel_writer_max_contract_repairs_invalid")


@dataclass(frozen=True, slots=True)
class NovelWriterTelemetry:
    chapter_id: str
    content_hash: str
    elapsed_seconds: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


class NovelWriterObserver(Protocol):
    def record(self, telemetry: NovelWriterTelemetry) -> None: ...


class LLMNovelWriterAdapter:
    def __init__(
        self,
        client: ModelClient,
        *,
        config: NovelWriterConfig = NovelWriterConfig(),
        observer: NovelWriterObserver | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._observer = observer
        self._runtime = RuntimeRunner()

    def write(self, request: NovelWritingRequest, admission: object) -> NovelDraft:
        self._require_admission_binding(request, admission)
        initial_refs = (("chapter", request.chapter_id), ("context", request.context_fingerprint))
        first = self._execute(
            request,
            build_novel_writer_messages(request, self._config.system_instruction),
            input_refs=initial_refs,
        )
        self._validate_content(first.output)
        results = [first]
        missing = _missing_information(request, first.output)
        if missing and self._config.max_contract_repairs == 1:
            repaired = self._execute(
                request,
                build_novel_writer_repair_messages(
                    request,
                    first.output,
                    missing,
                    self._config.system_instruction,
                ),
                input_refs=initial_refs + (("repair", "essential_information"),),
            )
            self._validate_content(repaired.output)
            results.append(repaired)

        draft = NovelDraft.from_content(results[-1].output)
        if self._observer is not None:
            self._observer.record(self._telemetry(request, draft, tuple(results)))
        return draft

    def _execute(
        self,
        request: NovelWritingRequest,
        messages: list[ModelMessage],
        *,
        input_refs: tuple[tuple[str, str], ...],
    ) -> RuntimeResult:
        try:
            return self._runtime.execute(
                RuntimeRequest(
                    task_id=request.chapter_id,
                    context_id=request.context_fingerprint,
                    capability="writing",
                    domain="novel",
                    model=str(getattr(self._client, "model", "unknown")),
                    messages=tuple(messages),
                    input_refs=input_refs,
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                ),
                self._client,
            )
        except RuntimeExecutionError as error:
            raise NovelWritingError("novel_writer_model_failed") from error.__cause__

    @staticmethod
    def _telemetry(
        request: NovelWritingRequest,
        draft: NovelDraft,
        results: tuple[RuntimeResult, ...],
    ) -> NovelWriterTelemetry:
        return NovelWriterTelemetry(
            chapter_id=request.chapter_id,
            content_hash=draft.content_hash,
            elapsed_seconds=_sum_optional_elapsed(tuple(
                result.reported_elapsed_seconds for result in results
            )),
            prompt_tokens=_sum_optional(tuple(
                None if result.usage is None else result.usage.prompt_tokens
                for result in results
            )),
            completion_tokens=_sum_optional(tuple(
                None if result.usage is None else result.usage.completion_tokens
                for result in results
            )),
            total_tokens=_sum_optional(tuple(
                None if result.usage is None else result.usage.total_tokens
                for result in results
            )),
        )

    @staticmethod
    def _require_admission_binding(request: NovelWritingRequest, admission: object) -> None:
        if getattr(admission, "chapter_id", None) != request.chapter_id:
            raise NovelWritingError("novel_writer_chapter_binding_mismatch")
        if getattr(admission, "context_fingerprint", None) != request.context_fingerprint:
            raise NovelWritingError("novel_writer_context_binding_mismatch")
        contract_id = getattr(admission, "contract_id", None)
        if not isinstance(contract_id, str) or not contract_id.strip():
            raise NovelWritingError("novel_writer_contract_id_missing")

    def _validate_content(self, content: str) -> None:
        normalized = content.strip()
        if not normalized:
            raise NovelWritingError("novel_draft_empty")
        if len(normalized) < self._config.minimum_reviewable_chars:
            raise NovelWritingError("novel_draft_below_reviewable_minimum")
        if normalized.startswith(("分析：", "提纲：")):
            raise NovelWritingError("novel_draft_contains_model_scaffolding")
        if normalized.startswith("```") and normalized.endswith("```"):
            raise NovelWritingError("novel_draft_contains_model_scaffolding")


def _missing_information(request: NovelWritingRequest, content: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        item
        for scene in request.chapter_contract.scene_plan.scenes
        for item in scene.essential_information
        if item not in content
    ))


def _sum_optional(values: tuple[int | None, ...]) -> int | None:
    return None if any(value is None for value in values) else sum(
        value for value in values if value is not None
    )


def _sum_optional_elapsed(values: tuple[float | None, ...]) -> float | None:
    return None if any(value is None for value in values) else sum(
        value for value in values if value is not None
    )
