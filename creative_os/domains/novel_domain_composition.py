from __future__ import annotations

from pathlib import Path

from creative_os.domains.novel_chapter_planner import NovelChapterPlanner
from creative_os.domains.novel_compiler import NovelCompiler
from creative_os.domains.novel_domain_service import NovelDomainService
from creative_os.domains.novel_lesson import NovelLessonBuilder
from creative_os.domains.novel_reviewer import NovelReviewer
from creative_os.domains.llm_novel_writer import (
    LLMNovelWriterAdapter,
    NovelWriterConfig,
    NovelWriterObserver,
)
from creative_os.domains.novel_writer_admission import NovelWriterAdmissionAdapter
from creative_os.domains.writer_admission import WriterAdmissionService
from creative_os.llm_writer import ModelClient, OpenAICompatibleClient


def build_novel_domain_service(
    project_root: str | Path,
    *,
    writer: object,
    baseline_resolver: object,
) -> NovelDomainService:
    """装配可运行的小说领域服务；正文生成器作为外部端口注入。"""
    if writer is None:
        raise ValueError("novel_domain_writer_missing")
    if baseline_resolver is None:
        raise ValueError("novel_domain_baseline_resolver_missing")
    admission_service = WriterAdmissionService(project_root, baseline_resolver)
    return NovelDomainService(
        planner=NovelChapterPlanner(),
        admission=NovelWriterAdmissionAdapter(admission_service),
        writer=writer,
        reviewer=NovelReviewer(),
        compiler=NovelCompiler(),
        lesson_builder=NovelLessonBuilder(),
    )


def build_llm_novel_domain_service(
    project_root: str | Path,
    *,
    baseline_resolver: object,
    client: ModelClient,
    writer_config: NovelWriterConfig | None = None,
    observer: NovelWriterObserver | None = None,
) -> NovelDomainService:
    """使用注入的模型客户端装配真实小说领域服务。"""
    writer = LLMNovelWriterAdapter(
        client,
        config=NovelWriterConfig() if writer_config is None else writer_config,
        observer=observer,
    )
    return build_novel_domain_service(
        project_root,
        writer=writer,
        baseline_resolver=baseline_resolver,
    )


def build_env_novel_domain_service(
    project_root: str | Path,
    *,
    baseline_resolver: object,
    env_file: str | Path | None = ".env",
    writer_config: NovelWriterConfig | None = None,
    observer: NovelWriterObserver | None = None,
) -> NovelDomainService:
    """在调用时读取环境并装配真实小说领域服务。"""
    client = OpenAICompatibleClient.from_env(env_file)
    return build_llm_novel_domain_service(
        project_root,
        baseline_resolver=baseline_resolver,
        client=client,
        writer_config=writer_config,
        observer=observer,
    )
