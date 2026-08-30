from __future__ import annotations

from creative_os.domains.novel_capabilities import NovelCapabilityCatalog
from creative_os.domains.novel_compile_model import NovelCompileRequest
from creative_os.domains.novel_review_model import NovelReviewRequest
from creative_os.domains.novel_run import NovelChapterRunRequest, NovelChapterRunResult
from creative_os.domains.novel_writer_admission import NovelWriterAdmissionError


class NovelDomainService:
    """小说领域稳定入口；负责组合能力，不复制各子系统业务逻辑。"""

    def __init__(
        self,
        *,
        planner: object,
        admission: object,
        writer: object,
        reviewer: object,
        compiler: object,
        lesson_builder: object,
    ) -> None:
        collaborators = {
            "planner": planner,
            "admission": admission,
            "writer": writer,
            "reviewer": reviewer,
            "compiler": compiler,
            "lesson_builder": lesson_builder,
        }
        for name, collaborator in collaborators.items():
            if collaborator is None:
                raise ValueError(f"novel_domain_collaborator_missing:{name}")
        self._planner = planner
        self._admission = admission
        self._writer = writer
        self._reviewer = reviewer
        self._compiler = compiler
        self._lesson_builder = lesson_builder
        self._capabilities = NovelCapabilityCatalog()

    def capabilities(self) -> NovelCapabilityCatalog:
        return self._capabilities

    def plan_chapter(self, request):
        return self._planner.plan(request)

    def admit_draft(self, request):
        return self._admission.admit(request)

    def write_draft(self, request, admission):
        return self._writer.write(request, admission)

    def review_draft(self, request):
        return self._reviewer.review(request)

    def compile_approved(self, request):
        return self._compiler.compile(request)

    def build_lesson_candidate(self, **kwargs):
        return self._lesson_builder.build(**kwargs)

    def run_chapter(self, request: NovelChapterRunRequest) -> NovelChapterRunResult:
        self._validate_run_request(request)
        plan_result = self.plan_chapter(request.planning)
        if not plan_result.approved:
            return NovelChapterRunResult(
                stage="planning_failed",
                plan_result=plan_result,
                failure_code=plan_result.blocking_codes[0],
            )
        try:
            admission = self.admit_draft(request.admission)
        except NovelWriterAdmissionError as error:
            return NovelChapterRunResult(
                stage="admission_failed",
                plan_result=plan_result,
                failure_code=str(error),
            )
        draft = self.write_draft(request.writing, admission)
        review_request = NovelReviewRequest(
            draft=draft.content,
            chapter_contract=request.writing.chapter_contract,
            boundary=request.boundary,
            adjacent_drafts=request.adjacent_drafts,
            character_changes=request.character_changes,
            consistency_findings=request.consistency_findings,
        )
        review_result = self.review_draft(review_request)
        if not review_result.passed:
            return NovelChapterRunResult(
                stage="review_failed",
                plan_result=plan_result,
                admission=admission,
                draft=draft,
                review_result=review_result,
                failure_code=review_result.blocking_codes[0],
            )
        compile_result = self.compile_approved(NovelCompileRequest(
            chapter_id=request.writing.chapter_id,
            source_chapter=request.source_chapter,
            draft=draft.content,
            content_hash=draft.content_hash,
            chapter_contract=request.writing.chapter_contract,
            review=review_result,
            character_changes=request.character_changes,
        ))
        return NovelChapterRunResult(
            stage="compile_candidate_ready",
            plan_result=plan_result,
            admission=admission,
            draft=draft,
            review_result=review_result,
            compile_result=compile_result,
        )

    @staticmethod
    def _validate_run_request(request: NovelChapterRunRequest) -> None:
        if not isinstance(request, NovelChapterRunRequest):
            raise TypeError("run_chapter requires NovelChapterRunRequest")
        if request.writing.context_fingerprint != request.admission.context_fingerprint:
            raise ValueError("novel_run_context_binding_mismatch")
        if request.writing.chapter_contract.scene_plan != request.planning.scene_plan:
            raise ValueError("novel_run_scene_plan_mismatch")
        if request.boundary != request.planning.boundary:
            raise ValueError("novel_run_boundary_mismatch")
