from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from creative_os.engine.context import Context
from creative_os.foundation.project import Milestone, MilestoneStatus, Project, ProjectPhase
from creative_os.foundation.state import ProjectState


class ProductionValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProjectBrief:
    name: str
    logline: str
    genre: str
    target_readers: str
    expected_words: str
    chapter_count: str
    core_hooks: list[str]
    constraints: list[str]
    current_stage: str
    status: str

    def validate(self) -> None:
        required = {
            "name": self.name,
            "logline": self.logline,
            "genre": self.genre,
            "target_readers": self.target_readers,
            "expected_words": self.expected_words,
            "chapter_count": self.chapter_count,
            "current_stage": self.current_stage,
            "status": self.status,
        }
        missing = [field_name for field_name, value in required.items() if not str(value).strip()]
        if missing:
            raise ProductionValidationError(f"ProjectBrief missing fields: {', '.join(missing)}")
        if not self.core_hooks:
            raise ProductionValidationError("ProjectBrief requires at least one core hook")


@dataclass(frozen=True, slots=True)
class VersionBaseline:
    code_version: str
    data_schema_version: str
    prompt_version: str
    domain_version: str
    agent_version: str
    model_config: dict[str, str]
    context_config: dict[str, int]
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True, slots=True)
class NovelMetadata:
    project_id: str
    planned_volumes: int
    planned_chapters: int
    words_per_chapter: str
    main_character_count: str
    major_scene_count: str
    main_plot_lines: int
    secondary_plot_lines: str


@dataclass(frozen=True, slots=True)
class ProductionLogEntry:
    id: str
    created_at: str
    input_task_id: str
    input_summary: str
    context_sources: list[str]
    capability: str
    output_summary: str
    review_result: str
    knowledge_updates: list[str]
    failure_reason: str | None = None
    human_intervention: str | None = None


class ProductionLog:
    def __init__(self, entries: list[ProductionLogEntry] | None = None) -> None:
        self._entries = list(entries or [])

    def record(
        self,
        input_task_id: str,
        input_summary: str,
        context_sources: list[str],
        capability: str,
        output_summary: str,
        review_result: str,
        knowledge_updates: list[str],
        failure_reason: str | None = None,
        human_intervention: str | None = None,
    ) -> ProductionLogEntry:
        if not input_task_id or not capability:
            raise ProductionValidationError("Production log requires task id and capability")
        entry = ProductionLogEntry(
            id=f"run-{len(self._entries) + 1:04d}",
            created_at=datetime.now(timezone.utc).isoformat(),
            input_task_id=input_task_id,
            input_summary=input_summary,
            context_sources=list(context_sources),
            capability=capability,
            output_summary=output_summary,
            review_result=review_result,
            knowledge_updates=list(knowledge_updates),
            failure_reason=failure_reason,
            human_intervention=human_intervention,
        )
        self._entries.append(entry)
        return entry

    def record_context_run(
        self,
        context: Context,
        capability: str,
        output_summary: str,
        review_result: str,
        knowledge_updates: list[str],
        failure_reason: str | None = None,
        human_intervention: str | None = None,
    ) -> ProductionLogEntry:
        return self.record(
            input_task_id=context.task.id,
            input_summary=context.user_input,
            context_sources=[item.id for item in context.knowledge],
            capability=capability,
            output_summary=output_summary,
            review_result=review_result,
            knowledge_updates=knowledge_updates,
            failure_reason=failure_reason,
            human_intervention=human_intervention,
        )

    def entries(self) -> list[ProductionLogEntry]:
        return list(self._entries)


@dataclass(slots=True)
class ValidationProject:
    project: Project
    state: ProjectState
    brief: ProjectBrief
    metadata: NovelMetadata
    baseline: VersionBaseline
    production_log: ProductionLog = field(default_factory=ProductionLog)

    def next_step(self) -> str:
        if not self.production_log.entries():
            return "创建 Project Proposal 并进入前期设计"
        return self.state.current_goal


class ProjectWorkspace:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(self, validation_project: ValidationProject) -> None:
        validation_project.brief.validate()
        self.root.mkdir(parents=True, exist_ok=True)
        self._write_json("project.json", _project_to_dict(validation_project.project))
        self._write_json("state.json", validation_project.state.compact())
        self._write_json("brief.json", asdict(validation_project.brief))
        self._write_json("metadata.json", asdict(validation_project.metadata))
        self._write_json("baseline.json", asdict(validation_project.baseline))
        self._write_jsonl("production_log.jsonl", [asdict(entry) for entry in validation_project.production_log.entries()])

    def load(self) -> ValidationProject:
        project = _project_from_dict(self._read_json("project.json"))
        state = ProjectState(**self._read_json("state.json"))
        brief = ProjectBrief(**self._read_json("brief.json"))
        metadata = NovelMetadata(**self._read_json("metadata.json"))
        baseline = VersionBaseline(**self._read_json("baseline.json"))
        log_entries = [ProductionLogEntry(**entry) for entry in self._read_jsonl("production_log.jsonl")]
        return ValidationProject(
            project=project,
            state=state,
            brief=brief,
            metadata=metadata,
            baseline=baseline,
            production_log=ProductionLog(log_entries),
        )

    def _write_json(self, name: str, payload: dict[str, Any]) -> None:
        (self.root / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _read_json(self, name: str) -> dict[str, Any]:
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def _write_jsonl(self, name: str, rows: list[dict[str, Any]]) -> None:
        text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
        (self.root / name).write_text(text, encoding="utf-8")

    def _read_jsonl(self, name: str) -> list[dict[str, Any]]:
        path = self.root / name
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def create_default_validation_project(code_version: str = "v1.0.0") -> ValidationProject:
    project = Project(
        id="novel-validation-001",
        name="雾城回声",
        domain="novel",
        phase=ProjectPhase.PROPOSAL,
        milestones=[
            Milestone(id="m1-project", title="项目立项", status=MilestoneStatus.DONE),
            Milestone(id="m2-agents", title="Agent 契约固定"),
            Milestone(id="m3-design", title="前期设计通过"),
            Milestone(id="m4-first-chapter", title="第一章闭环"),
            Milestone(id="m5-ten-chapters", title="前十章连续创作"),
            Milestone(id="m6-draft-complete", title="初稿完成"),
            Milestone(id="m7-full-review", title="全书 Review"),
            Milestone(id="m8-v1-1", title="V1.1 验收"),
        ],
    )
    state = ProjectState(
        current_phase="Proposal",
        current_task_id="proposal-001",
        current_goal="完成 Project Proposal",
        active_domain="novel",
        risks=["尚未完成 Story Bible", "尚未完成前十章 Scene Plan"],
    )
    brief = ProjectBrief(
        name="雾城回声",
        logline="一名失忆修灯师进入禁止点灯的雾城，必须找回妹妹失踪真相，同时证明光并非灾难源头。",
        genre="悬疑科幻中短篇",
        target_readers="喜欢强设定、悬疑推进和人物成长的青年读者",
        expected_words="8万-12万字",
        chapter_count="36章",
        core_hooks=["禁灯之城", "失踪妹妹", "光源真相", "记忆被人为改写"],
        constraints=["单主线推进", "不使用复杂时间循环", "主要人物控制在 3-8 人", "每章由 Scene Task 驱动"],
        current_stage="V1 Production Validation / M1",
        status="active",
    )
    metadata = NovelMetadata(
        project_id=project.id,
        planned_volumes=2,
        planned_chapters=36,
        words_per_chapter="2200-3200",
        main_character_count="5-7",
        major_scene_count="12-16",
        main_plot_lines=1,
        secondary_plot_lines="2",
    )
    baseline = VersionBaseline(
        code_version=code_version,
        data_schema_version="v1",
        prompt_version="v1",
        domain_version="novel-v1",
        agent_version="production-agent-v1",
        model_config={"provider": "manual-or-external", "model": "not-bound-in-v1-runtime"},
        context_config={"max_items": 8, "max_chars": 12000},
    )
    return ValidationProject(project=project, state=state, brief=brief, metadata=metadata, baseline=baseline)


def _project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "domain": project.domain,
        "phase": project.phase.value,
        "milestones": [
            {"id": milestone.id, "title": milestone.title, "status": milestone.status.value}
            for milestone in project.milestones
        ],
    }


def _project_from_dict(payload: dict[str, Any]) -> Project:
    return Project(
        id=payload["id"],
        name=payload["name"],
        domain=payload["domain"],
        phase=ProjectPhase(payload["phase"]),
        milestones=[
            Milestone(id=item["id"], title=item["title"], status=MilestoneStatus(item["status"]))
            for item in payload.get("milestones", [])
        ],
    )
