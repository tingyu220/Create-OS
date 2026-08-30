from __future__ import annotations

from dataclasses import dataclass

from creative_os.domains.novel_chapter_boundary import ChapterBoundary
from creative_os.domains.novel_chapter_planner import ChapterPlanningRequest, ChapterPlanResult
from creative_os.domains.novel_compile_model import NovelCompileResult
from creative_os.domains.novel_review_model import (
    CharacterStateProposal,
    ConsistencyFinding,
    NovelReviewResult,
)
from creative_os.domains.novel_writer import NovelDraft, NovelWritingRequest
from creative_os.domains.novel_writer_admission import NovelAdmissionRequest


@dataclass(frozen=True, slots=True)
class NovelChapterRunRequest:
    planning: ChapterPlanningRequest
    admission: NovelAdmissionRequest
    writing: NovelWritingRequest
    boundary: ChapterBoundary
    source_chapter: str
    adjacent_drafts: tuple[str, ...] = ()
    character_changes: tuple[CharacterStateProposal, ...] = ()
    consistency_findings: tuple[ConsistencyFinding, ...] = ()


@dataclass(frozen=True, slots=True)
class NovelChapterRunResult:
    stage: str
    plan_result: ChapterPlanResult
    admission: object | None = None
    draft: NovelDraft | None = None
    review_result: NovelReviewResult | None = None
    compile_result: NovelCompileResult | None = None
    failure_code: str | None = None

