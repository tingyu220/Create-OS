from creative_os.writer_workspace_dto import (
    WriterChapterDTO,
    WriterChapterEnvelope,
    WriterSourceDTO,
    WriterSourceRole,
    WriterVersionDTO,
    encode_writer_chapter,
)
from creative_os.workspace_dto import Freshness


def test_writer_dto_marks_formal_sources_read_only_and_draft_editable():
    published = WriterSourceDTO(WriterSourceRole.PUBLISHED, "已发布章节", False, "published:chapter-079")
    draft = WriterSourceDTO(WriterSourceRole.WORKING_DRAFT, "当前工作稿", True, "draft:chapter-079")

    assert published.editable is False
    assert draft.editable is True


def test_writer_encoder_preserves_version_and_traceability_without_internal_domain_objects():
    source = WriterSourceDTO(
        WriterSourceRole.WORKING_DRAFT,
        "当前工作稿",
        True,
        "draft:chapter-079",
        "working-drafts/chapter_079/v2.md",
        "hash-v2",
    )
    version = WriterVersionDTO(2, "hash-v2", "2026-09-25T10:00:00Z", "author", 1, "draft:chapter-079")
    envelope = WriterChapterEnvelope(
        WriterChapterDTO("civilization-ascension", 79, "第七十九章", "正文", source, version, Freshness.FRESH, ("source:chapter-079",)),
        Freshness.FRESH,
    )

    encoded = encode_writer_chapter(envelope)

    assert encoded["chapter"]["source"]["role"] == "working_draft"
    assert encoded["chapter"]["source"]["editable"] is True
    assert encoded["chapter"]["version"]["version"] == 2
    assert encoded["chapter"]["source_refs"] == ["source:chapter-079"]
    assert "ProjectSnapshot" not in repr(encoded)

