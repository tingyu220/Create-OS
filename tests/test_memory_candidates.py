from creative_os.memory.candidates import CandidateExtractionInput, extract_candidates
from creative_os.memory.model import MemoryScope, MemoryStatus


def test_repeated_issue_creates_scoped_candidate_not_active_memory():
    result = extract_candidates(
        CandidateExtractionInput(
            task_id="chapter-004",
            project_id="文明升阶",
            domain="novel",
            issues=["time_word_opener", "time_word_opener"],
            attempts=2,
            human_feedback="章节开头不要总用时间词",
            source_ids=["review-004-a", "review-004-b"],
        )
    )

    assert len(result) == 1
    assert result[0].status == MemoryStatus.CANDIDATE
    assert result[0].scope == MemoryScope.DOMAIN
    assert result[0].scope_id == "novel"
    assert result[0].content == "章节开头不要总用时间词"
    assert {evidence.source_id for evidence in result[0].evidence} == {"review-004-a", "review-004-b"}


def test_single_unconfirmed_issue_does_not_become_experience():
    result = extract_candidates(
        CandidateExtractionInput(
            task_id="chapter-001",
            project_id="文明升阶",
            domain="novel",
            issues=["one_off_issue"],
            attempts=1,
            human_feedback="",
            source_ids=["review-001"],
        )
    )

    assert result == []


def test_same_input_produces_stable_candidate_id():
    payload = CandidateExtractionInput(
        task_id="chapter-004",
        project_id="文明升阶",
        domain="novel",
        issues=[" time_word_opener ", "TIME_WORD_OPENER"],
        attempts=2,
        human_feedback="章节开头不要总用时间词",
        source_ids=["review-004-a"],
    )

    assert extract_candidates(payload)[0].id == extract_candidates(payload)[0].id
