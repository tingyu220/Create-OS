"""Writer Agent 使用的只读创作上下文与结构化决策契约。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CreativeDecision:
    decision_id: str
    intent: str
    target_chapter: int
    context_refs: tuple[str, ...]
    observations: tuple[str, ...] = ()
    strategy: str = ""
    actions: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class CreativeContext:
    intent: str
    target_chapter: int
    current_draft: str
    current_formal: str
    recent_chapters: tuple[int, ...]
    source_refs: tuple[str, ...]
    decision: CreativeDecision
    observations: tuple[str, ...] = ()
    experience_prompt: str = ""
    experience_context: dict = field(default_factory=dict)
    current_draft_version: int | None = None
    creative_state: dict = field(default_factory=dict)


class CreativeContextBuilder:
    """只读读取 Writer 需要的最小上下文，不写入领域事实。"""

    def __init__(self, project_root: str | Path, recent_limit: int = 3, *, project_id: str | None = None) -> None:
        self.root = Path(project_root)
        self.recent_limit = recent_limit
        self.project_id = project_id or self.root.resolve().name

    def build(self, intent: str, target_chapter: int, *, task_id: str = "writer-context") -> CreativeContext:
        if not intent.strip() or target_chapter <= 0:
            raise ValueError("creative_context_request_invalid")
        final_root = self.root / "production" / "final_chapters"
        formal_numbers = sorted(int(path.stem.split("_")[-1]) for path in final_root.glob("chapter_*.md")) if final_root.exists() else []
        recent = tuple(number for number in formal_numbers if number < target_chapter)[-self.recent_limit:]
        refs = tuple(f"production/final_chapters/chapter_{number:03d}.md" for number in recent)
        projection_path = self.root / ".creative_os" / "projection" / "bundle.json"
        if projection_path.exists():
            refs += (".creative_os/projection/bundle.json",)
        draft_path = self.root / ".creative_os" / "writer" / "drafts" / f"chapter_{target_chapter:03d}.jsonl"
        draft = ""
        draft_version = None
        if draft_path.exists():
            record = json.loads(draft_path.read_text(encoding="utf-8").splitlines()[-1])
            draft = str(record.get("content", ""))
            draft_version = record.get("version")
            refs += (f".creative_os/writer/drafts/chapter_{target_chapter:03d}.jsonl",)
        formal_path = final_root / f"chapter_{target_chapter:03d}.md"
        formal = formal_path.read_text(encoding="utf-8") if formal_path.exists() else ""
        if formal:
            refs += (f"production/final_chapters/chapter_{target_chapter:03d}.md",)
        from creative_os.writer_experience_context import compile_writer_experience
        experience_prompt, experience_context = compile_writer_experience(self.root, self.project_id, target_chapter, task_id)
        refs += tuple(item["source_ref"] for item in experience_context["selected"])
        creative_state: dict[str, object] = {}
        for name in ("import/conflicts.json", "knowledge/imported_active.json", "import/active_baseline.json"):
            path = self.root / ".creative_os" / name
            if not path.exists():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            creative_state[name] = value
            refs += (f".creative_os/{name}",)
        decision = CreativeDecision(
            decision_id=f"decision-{uuid4().hex}", intent=intent.strip(), target_chapter=target_chapter,
            context_refs=refs, created_at=datetime.now(timezone.utc).isoformat(),
        )
        return CreativeContext(intent.strip(), target_chapter, draft, formal, recent, refs, decision,
                               experience_prompt=experience_prompt, experience_context=experience_context,
                               current_draft_version=draft_version, creative_state=creative_state)
