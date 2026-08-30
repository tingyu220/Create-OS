from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from creative_os.domains.novel_writer import NovelDraft, NovelWritingError, NovelWritingRequest
from creative_os.domains.novel_writer_prompt import (
    DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION,
    build_novel_writer_messages,
)
from creative_os.llm_writer import ModelClient
from creative_os.runtime import RuntimeExecutionError, RuntimeRequest, RuntimeRunner


@dataclass(frozen=True, slots=True)
class NovelWriterConfig:
    temperature: float = 0.7
    max_tokens: int = 6000
    minimum_reviewable_chars: int = 500
    system_instruction: str = DEFAULT_NOVEL_WRITER_SYSTEM_INSTRUCTION


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
        messages = build_novel_writer_messages(request, self._config.system_instruction)
        try:
            result = self._runtime.execute(
                RuntimeRequest(
                    task_id=request.chapter_id,
                    context_id=request.context_fingerprint,
                    capability="writing",
                    domain="novel",
                    model=str(getattr(self._client, "model", "unknown")),
                    messages=tuple(messages),
                    input_refs=(("chapter", request.chapter_id), ("context", request.context_fingerprint)),
                    temperature=self._config.temperature,
                    max_tokens=self._config.max_tokens,
                ),
                self._client,
            )
        except RuntimeExecutionError as error:
            raise NovelWritingError("novel_writer_model_failed") from error.__cause__

        self._validate_content(result.output)
        draft = NovelDraft.from_content(result.output)
        if self._observer is not None:
            self._observer.record(
                NovelWriterTelemetry(
                    chapter_id=request.chapter_id,
                    content_hash=draft.content_hash,
                    elapsed_seconds=result.reported_elapsed_seconds,
                    prompt_tokens=None if result.usage is None else result.usage.prompt_tokens,
                    completion_tokens=None if result.usage is None else result.usage.completion_tokens,
                    total_tokens=None if result.usage is None else result.usage.total_tokens,
                )
            )
        return draft

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
