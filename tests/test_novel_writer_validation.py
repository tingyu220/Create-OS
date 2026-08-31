from dataclasses import replace
from pathlib import Path

from creative_os.llm_metrics import LLMUsage, TimedCompletion
from creative_os.domains.novel_validation_fixture import load_independent_validation_case


PROJECT = Path(__file__).resolve().parents[1] / "projects" / "novel_domain_validation"
FIXTURE = PROJECT / "validation" / "independent_short_story.json"


class FakeClient:
    model = "fixture-writer"

    def __init__(self, completion):
        self._completion = completion

    def complete(self, messages, *, temperature, max_tokens):
        return self._completion


def test_fake_validation_reaches_compile_candidate_with_redacted_fixed_report():
    from creative_os.novel_writer_validation import run_independent_writer_validation

    case = load_independent_validation_case(FIXTURE)
    report = run_independent_writer_validation(
        case,
        FakeClient(TimedCompletion(case.fake_draft.content, 1.5, LLMUsage(11, 22, 33))),
        mode="fake",
    )

    assert report.stage == "compile_candidate_ready"
    assert report.review_passed is True
    assert report.canon_patch_count > 0
    assert report.state_candidate_count > 0
    assert report.provider_kind == "fake"
    assert report.model == "fixture-writer"
    assert report.elapsed_seconds == 1.5
    assert report.total_tokens == 33
    assert set(report.to_dict()) == {
        "mode", "provider_kind", "model", "chapter_id", "stage", "review_passed",
        "blocking_codes", "content_hash", "elapsed_seconds", "prompt_tokens",
        "completion_tokens", "total_tokens", "canon_patch_count", "state_candidate_count",
    }
    rendered = str(report.to_dict()).lower()
    assert "api_key" not in rendered
    assert "authorization" not in rendered


def test_validation_rejects_unsupported_mode_before_model_execution():
    from creative_os.novel_writer_validation import run_independent_writer_validation

    case = load_independent_validation_case(FIXTURE)

    try:
        run_independent_writer_validation(case, FakeClient(case.fake_draft.content), mode="other")
    except ValueError as error:
        assert str(error) == "novel_writer_validation_mode_invalid"
    else:
        raise AssertionError("unsupported mode must be rejected")


def test_validation_reports_planning_or_review_blocking_codes_without_draft_content():
    from creative_os.novel_writer_validation import run_independent_writer_validation

    case = load_independent_validation_case(FIXTURE)
    report = run_independent_writer_validation(case, FakeClient("无关正文" * 300), mode="fake")

    assert report.stage == "review_failed"
    assert report.review_passed is False
    assert report.blocking_codes == ("essential_information_missing",)
    assert report.content_hash is not None


def test_validation_preserves_early_failure_code_in_fixed_report():
    from creative_os.novel_writer_validation import run_independent_writer_validation

    case = load_independent_validation_case(FIXTURE)
    blocked_case = replace(case, boundary=replace(
        case.boundary,
        dialogue_closed=False,
        dramatic_unit_closed=False,
    ))
    report = run_independent_writer_validation(
        blocked_case,
        FakeClient(blocked_case.fake_draft.content),
        mode="fake",
    )

    assert report.stage == "planning_failed"
    assert report.review_passed is False
    assert report.blocking_codes == ("dialogue_cut",)
    assert report.content_hash is None
