import hashlib

import pytest

from creative_os.domains.novel_compile_model import NovelCompileRequest
from creative_os.domains.novel_compiler import NovelCompileError, NovelCompiler
from creative_os.domains.novel_review_model import CharacterStateProposal, NovelReviewResult
from tests.test_novel_reviewer import _request


def _compile_request(*, review=None, content_hash=None):
    review_request = _request(character_changes=(
        CharacterStateProposal("林子轩", "承担停机代价", ("林子轩承担停机代价",)),
    ))
    digest = hashlib.sha256(review_request.draft.encode("utf-8")).hexdigest()
    return NovelCompileRequest(
        chapter_id="chapter_007",
        source_chapter="production/final_chapters/chapter_007.md",
        draft=review_request.draft,
        content_hash=content_hash or digest,
        chapter_contract=review_request.chapter_contract,
        review=review or NovelReviewResult((), ()),
        character_changes=review_request.character_changes,
    )


def test_compiler_rejects_unapproved_draft():
    failed = NovelReviewResult((), ("timeline_conflict",))

    with pytest.raises(NovelCompileError, match="review_not_passed"):
        NovelCompiler().compile(_compile_request(review=failed))


def test_compiler_rejects_content_hash_drift():
    with pytest.raises(NovelCompileError, match="draft_hash_mismatch"):
        NovelCompiler().compile(_compile_request(content_hash="f" * 64))


def test_compiler_emits_evidence_bound_candidates():
    request = _compile_request()
    result = NovelCompiler().compile(request)

    assert result.fingerprint
    assert result.canon_patches
    assert all(patch.evidence for patch in result.canon_patches)
    assert result.state_changes
    assert all(change.evidence for change in result.state_changes)
    assert result.next_task_input.previous_chapter_hash == request.content_hash
    assert result.next_task_input.required_open_hooks == tuple(
        request.chapter_contract.foreshadow_actions.values
    )
