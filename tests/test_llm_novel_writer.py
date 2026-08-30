from dataclasses import dataclass, replace

import pytest

from creative_os.domains.narrative_decision import ChapterContract
from creative_os.domains.novel_writer import NovelWritingRequest
from creative_os.llm_metrics import LLMUsage, TimedCompletion
from tests.test_narrative_director import _v2_decision
from tests.test_novel_scene_contract import _complete_scene


@dataclass(frozen=True, slots=True)
class Admission:
    chapter_id: str
    context_fingerprint: str
    contract_id: str


class FakeClient:
    def __init__(self, completion):
        self.completion = completion

    def complete(self, messages, *, temperature, max_tokens):
        return self.completion


class RaisingClient:
    def complete(self, messages, *, temperature, max_tokens):
        raise RuntimeError("model unavailable")


class RecordingObserver:
    def __init__(self):
        self.items = []

    def record(self, telemetry):
        self.items.append(telemetry)


@pytest.fixture
def writing_request() -> NovelWritingRequest:
    decision = _v2_decision()
    scene_plan = replace(decision.chapter_contract.scene_plan, scenes=(_complete_scene(),))
    contract: ChapterContract = replace(decision.chapter_contract, scene_plan=scene_plan)
    return NovelWritingRequest("chapter_001", contract, "a" * 64, "保持克制的现实语气")


@pytest.fixture
def admission(writing_request) -> Admission:
    return Admission(writing_request.chapter_id, writing_request.context_fingerprint, "contract-001")


def test_adapter_returns_hashed_draft_and_emits_telemetry(writing_request, admission):
    from creative_os.domains.llm_novel_writer import LLMNovelWriterAdapter

    client = FakeClient(TimedCompletion("第一段。\n\n" + "正文" * 300, 1.25, LLMUsage(10, 20, 30)))
    observer = RecordingObserver()
    writer = LLMNovelWriterAdapter(client, observer=observer)
    draft = writer.write(writing_request, admission)
    assert draft.content.startswith("第一段")
    assert len(draft.content_hash) == 64
    assert observer.items[0].elapsed_seconds == 1.25
    assert observer.items[0].total_tokens == 30


def test_adapter_accepts_plain_string_completion(writing_request, admission):
    from creative_os.domains.llm_novel_writer import LLMNovelWriterAdapter

    observer = RecordingObserver()
    draft = LLMNovelWriterAdapter(FakeClient("正文" * 300), observer=observer).write(
        writing_request,
        admission,
    )
    assert draft.content == "正文" * 300
    assert observer.items[0].elapsed_seconds >= 0
    assert observer.items[0].total_tokens is None


@pytest.mark.parametrize("mutation,code", [
    ("chapter", "novel_writer_chapter_binding_mismatch"),
    ("context", "novel_writer_context_binding_mismatch"),
    ("empty", "novel_draft_empty"),
    ("short", "novel_draft_below_reviewable_minimum"),
    ("analysis", "novel_draft_contains_model_scaffolding"),
])
def test_adapter_fails_closed(mutation, code, writing_request, admission):
    from creative_os.domains.llm_novel_writer import LLMNovelWriterAdapter
    from creative_os.domains.novel_writer import NovelWritingError

    effective_admission = admission
    content = "正文" * 300
    if mutation == "chapter":
        effective_admission = replace(admission, chapter_id="chapter_002")
    elif mutation == "context":
        effective_admission = replace(admission, context_fingerprint="b" * 64)
    elif mutation == "empty":
        content = "   "
    elif mutation == "short":
        content = "正文" * 200
    elif mutation == "analysis":
        content = "分析：" + "正文" * 300

    with pytest.raises(NovelWritingError, match=code):
        LLMNovelWriterAdapter(FakeClient(content)).write(writing_request, effective_admission)


@pytest.mark.parametrize("content", ["```\n" + "正文" * 300 + "\n```", "提纲：" + "正文" * 300])
def test_adapter_rejects_wrapped_or_scaffolding_output(content, writing_request, admission):
    from creative_os.domains.llm_novel_writer import LLMNovelWriterAdapter
    from creative_os.domains.novel_writer import NovelWritingError

    with pytest.raises(NovelWritingError, match="novel_draft_contains_model_scaffolding"):
        LLMNovelWriterAdapter(FakeClient(content)).write(writing_request, admission)


def test_adapter_wraps_model_failure(writing_request, admission):
    from creative_os.domains.llm_novel_writer import LLMNovelWriterAdapter
    from creative_os.domains.novel_writer import NovelWritingError

    with pytest.raises(NovelWritingError, match="novel_writer_model_failed") as captured:
        LLMNovelWriterAdapter(RaisingClient()).write(writing_request, admission)
    assert isinstance(captured.value.__cause__, RuntimeError)


def test_adapter_requires_admission_contract_id(writing_request, admission):
    from creative_os.domains.llm_novel_writer import LLMNovelWriterAdapter
    from creative_os.domains.novel_writer import NovelWritingError

    with pytest.raises(NovelWritingError, match="novel_writer_contract_id_missing"):
        LLMNovelWriterAdapter(FakeClient("正文" * 300)).write(
            writing_request,
            replace(admission, contract_id=" "),
        )
