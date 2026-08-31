from dataclasses import dataclass, replace

import pytest

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


@dataclass(frozen=True, slots=True)
class _AdmissionToken:
    chapter_id: str
    contract_id: str
    contract_content_hash: str
    context_fingerprint: str


class _Admission:
    def __init__(self, writing):
        self.calls = 0
        self.writing = writing

    def admit(self, request):
        self.calls += 1
        return _AdmissionToken(
            chapter_id=self.writing.chapter_id,
            contract_id=request.contract_id,
            contract_content_hash=self.writing.contract_content_hash,
            context_fingerprint=request.context_fingerprint,
        )


class _Writer:
    def __init__(self, content):
        self.content = content
        self.calls = 0

    def write(self, request, admission):
        self.calls += 1
        assert admission.context_fingerprint == request.context_fingerprint
        return NovelDraft.from_content(self.content)


def _service(content, writing):
    admission = _Admission(writing)
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
    decision = replace(decision, chapter_contract=contract)
    writing = NovelWritingRequest.from_narrative_decision(
        decision,
        context_fingerprint="f" * 64,
        instruction="按合同完成正文",
    )
    request = NovelChapterRunRequest(
        planning=ChapterPlanningRequest(scene_plan=scene_plan, boundary=boundary),
        admission=NovelAdmissionRequest(decision.contract_id, "f" * 64, "run-007"),
        writing=writing,
        boundary=boundary,
        source_chapter="production/final_chapters/chapter_007.md",
    )
    return request


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
    request = _run_request(boundary=_boundary(
        dialogue_closed=False,
        dramatic_unit_closed=False,
        estimated_chinese_chars=449,
    ))
    service, admission, writer = _service("现场确认旧图缺失，试验暂停。", request.writing)

    result = service.run_chapter(request)

    assert result.stage == "planning_failed"
    assert result.compile_result is None
    assert admission.calls == 0
    assert writer.calls == 0


def test_domain_service_stops_before_compile_when_review_fails():
    request = _run_request(boundary=_boundary())
    service, _admission, _writer = _service("正文没有呈现合同要求的必要信息。", request.writing)

    result = service.run_chapter(request)

    assert result.stage == "review_failed"
    assert "essential_information_missing" in result.review_result.blocking_codes
    assert result.compile_result is None


def test_domain_service_completes_approved_chapter_cycle():
    request = _run_request(boundary=_boundary())
    service, admission, writer = _service(
        "现场确认旧图缺失。\n\n林子轩承担停机代价，试验暂停。",
        request.writing,
    )

    result = service.run_chapter(request)

    assert result.stage == "compile_candidate_ready"
    assert result.compile_result.state_changes
    assert result.compile_result.canon_patches
    assert admission.calls == 1
    assert writer.calls == 1


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"contract_id": "unrelated-contract"}, "novel_writer_contract_id_binding_mismatch"),
        ({"contract_content_hash": "0" * 64}, "novel_writer_contract_hash_binding_mismatch"),
    ],
)
def test_domain_service_rejects_unrelated_admission_token_before_writer(changes, code):
    request = _run_request(boundary=_boundary())
    service, _admission, writer = _service("正文", request.writing)
    token = _AdmissionToken(
        chapter_id=request.writing.chapter_id,
        contract_id=request.writing.contract_id,
        contract_content_hash=request.writing.contract_content_hash,
        context_fingerprint=request.writing.context_fingerprint,
    )

    with pytest.raises(ValueError, match=code):
        service.write_draft(request.writing, replace(token, **changes))
    assert writer.calls == 0


def test_domain_service_rejects_admission_request_for_unrelated_contract():
    request = _run_request(boundary=_boundary())
    service, admission, writer = _service("正文", request.writing)
    request = replace(
        request,
        admission=replace(request.admission, contract_id="unrelated-contract"),
    )

    with pytest.raises(ValueError, match="novel_run_contract_id_binding_mismatch"):
        service.run_chapter(request)
    assert admission.calls == 0
    assert writer.calls == 0
