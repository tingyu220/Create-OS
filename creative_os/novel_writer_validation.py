"""独立小说 Writer 验收的内存闭环运行器。"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from creative_os.domains.llm_novel_writer import (
    LLMNovelWriterAdapter,
    NovelWriterObserver,
    NovelWriterTelemetry,
)
from creative_os.domains.novel_chapter_planner import NovelChapterPlanner
from creative_os.domains.novel_compiler import NovelCompiler
from creative_os.domains.novel_domain_service import NovelDomainService
from creative_os.domains.novel_lesson import NovelLessonBuilder
from creative_os.domains.novel_reviewer import NovelReviewer
from creative_os.domains.novel_run import NovelChapterRunRequest
from creative_os.domains.novel_validation_fixture import IndependentNovelValidationCase


_VALIDATION_MODES = frozenset({"fake", "live"})


@dataclass(frozen=True, slots=True)
class NovelWriterValidationReport:
    mode: str
    provider_kind: str
    model: str
    chapter_id: str
    stage: str
    review_passed: bool
    blocking_codes: tuple[str, ...]
    content_hash: str | None
    elapsed_seconds: float | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    canon_patch_count: int
    state_candidate_count: int

    def to_dict(self) -> dict[str, object]:
        """仅投影允许审计的标量字段，避免泄露客户端或原始响应。"""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class _ValidationAdmissionToken:
    """仅供夹具验收使用的内存令牌，不代表持久化审批记录。"""

    chapter_id: str
    contract_id: str
    context_fingerprint: str


class _ValidationAdmission:
    def __init__(self, case: IndependentNovelValidationCase) -> None:
        self._case = case

    def admit(self, request: object) -> _ValidationAdmissionToken:
        if request != self._case.admission:
            raise ValueError("validation_admission_request_mismatch")
        return _ValidationAdmissionToken(
            chapter_id=self._case.writing.chapter_id,
            contract_id=self._case.admission.contract_id,
            context_fingerprint=self._case.writing.context_fingerprint,
        )


class _TelemetryCollector(NovelWriterObserver):
    def __init__(self) -> None:
        self.item: NovelWriterTelemetry | None = None

    def record(self, telemetry: NovelWriterTelemetry) -> None:
        self.item = telemetry


def run_independent_writer_validation(
    case: IndependentNovelValidationCase,
    client: object,
    *,
    mode: str,
) -> NovelWriterValidationReport:
    """执行独立夹具的规划、写作、审查与候选编译闭环。"""
    if mode not in _VALIDATION_MODES:
        raise ValueError("novel_writer_validation_mode_invalid")

    telemetry = _TelemetryCollector()
    service = NovelDomainService(
        planner=NovelChapterPlanner(),
        admission=_ValidationAdmission(case),
        writer=LLMNovelWriterAdapter(client, observer=telemetry),
        reviewer=NovelReviewer(),
        compiler=NovelCompiler(),
        lesson_builder=NovelLessonBuilder(),
    )
    result = service.run_chapter(NovelChapterRunRequest(
        planning=case.planning_request,
        admission=case.admission,
        writing=case.writing,
        boundary=case.boundary,
        source_chapter=case.source_chapter,
        character_changes=case.character_changes,
    ))
    review = result.review_result
    compile_result = result.compile_result
    return NovelWriterValidationReport(
        mode=mode,
        provider_kind="fake" if mode == "fake" else "openai_compatible",
        model=str(getattr(client, "model", "unknown")),
        chapter_id=case.writing.chapter_id,
        stage=result.stage,
        review_passed=bool(review and review.passed),
        blocking_codes=(
            review.blocking_codes
            if review is not None
            else (() if result.failure_code is None else (result.failure_code,))
        ),
        content_hash=None if result.draft is None else result.draft.content_hash,
        elapsed_seconds=None if telemetry.item is None else telemetry.item.elapsed_seconds,
        prompt_tokens=None if telemetry.item is None else telemetry.item.prompt_tokens,
        completion_tokens=None if telemetry.item is None else telemetry.item.completion_tokens,
        total_tokens=None if telemetry.item is None else telemetry.item.total_tokens,
        canon_patch_count=0 if compile_result is None else len(compile_result.canon_patches),
        state_candidate_count=0 if compile_result is None else len(compile_result.state_changes),
    )
