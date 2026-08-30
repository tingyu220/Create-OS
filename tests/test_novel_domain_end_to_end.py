from dataclasses import replace

from creative_os.domains.novel_chapter_boundary import ChapterBoundary
from creative_os.domains.novel_chapter_planner import ChapterPlanningRequest, NovelChapterPlanner
from creative_os.domains.novel_compiler import NovelCompiler
from creative_os.domains.novel_domain_service import NovelDomainService
from creative_os.domains.novel_reviewer import NovelReviewer
from creative_os.domains.novel_run import NovelChapterRunRequest
from creative_os.domains.novel_writer import NovelDraft, NovelWritingRequest
from creative_os.domains.novel_writer_admission import NovelAdmissionRequest
from tests.test_novel_scene_contract import _complete_scene
from tests.test_narrative_director import _v2_decision


class _Admission:
    def __init__(self):
        self.calls = 0

    def admit(self, request):
        self.calls += 1
        return {"contract_id": request.contract_id, "context": request.context_fingerprint}


class _Writer:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def write(self, request, admission):
        self.calls += 1
        assert admission["context"] == request.context_fingerprint
        return NovelDraft.from_content(self.content)


def _service(content):
    admission = _Admission()
    writer = _Writer(content)
    service = NovelDomainService(
        planner=NovelChapterPlanner(),
        admission=admission,
        writer=writer,
        reviewer=NovelReviewer(),
        compiler=NovelCompiler(),
        lesson_builder=object(),
    )
    return service, admission, writer


def _run_request(*, boundary):
    decision = _v2_decision()
    scene_plan = replace(decision.chapter_contract.scene_plan, scenes=(_complete_scene(),))
    contract = replace(decision.chapter_contract, scene_plan=scene_plan)
    return NovelChapterRunRequest(
        planning=ChapterPlanningRequest(scene_plan=scene_plan, boundary=boundary),
        admission=NovelAdmissionRequest(decision.contract_id, "f" * 64, "run-007"),
        writing=NovelWritingRequest("chapter_007", contract, "f" * 64, "按合同完成正文"),
        boundary=boundary,
        source_chapter="production/final_chapters/chapter_007.md",
    )


def _boundary(**changes):
    values = {
        "entry_state": "主角进入现场",
        "exit_state": "主角停机并获得证据",
        "ending_function": "reveal",
        "dialogue_closed": True,
        "dramatic_unit_closed": True,
        "estimated_chinese_chars": 3400,
    }
    values.update(changes)
    return ChapterBoundary(**values)


def test_domain_service_stops_before_writer_when_planning_fails():
    service, admission, writer = _service("现场确认旧图缺失，试验暂停。")
    request = _run_request(boundary=_boundary(
        dialogue_closed=False,
        dramatic_unit_closed=False,
        estimated_chinese_chars=449,
    ))

    result = service.run_chapter(request)

    assert result.stage == "planning_failed"
    assert result.compile_result is None
    assert admission.calls == 0
    assert writer.calls == 0


def test_domain_service_stops_before_compile_when_review_fails():
    service, _admission, _writer = _service("正文没有呈现合同要求的必要信息。")

    result = service.run_chapter(_run_request(boundary=_boundary()))

    assert result.stage == "review_failed"
    assert "essential_information_missing" in result.review_result.blocking_codes
    assert result.compile_result is None


def test_domain_service_completes_approved_chapter_cycle():
    service, admission, writer = _service("现场确认旧图缺失。\n\n林子轩承担停机代价，试验暂停。")

    result = service.run_chapter(_run_request(boundary=_boundary()))

    assert result.stage == "compile_candidate_ready"
    assert result.compile_result.state_changes
    assert result.compile_result.canon_patches
    assert admission.calls == 1
    assert writer.calls == 1
