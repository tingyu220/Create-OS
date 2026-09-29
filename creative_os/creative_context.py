"""Writer Agent 使用的只读创作上下文与结构化决策契约。"""

from __future__ import annotations

from dataclasses import dataclass
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


class CreativeContextBuilder:
    """只读读取 Writer 需要的最小上下文，不写入领域事实。"""

    def __init__(self, project_root: str | Path, recent_limit: int = 3) -> None:
        self.root = Path(project_root)
        self.recent_limit = recent_limit

    def build(self, intent: str, target_chapter: int) -> CreativeContext:
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
        if draft_path.exists():
            record = json.loads(draft_path.read_text(encoding="utf-8").splitlines()[-1])
            draft = str(record.get("content", ""))
            refs += (f".creative_os/writer/drafts/chapter_{target_chapter:03d}.jsonl",)
        formal_path = final_root / f"chapter_{target_chapter:03d}.md"
        formal = formal_path.read_text(encoding="utf-8") if formal_path.exists() else ""
        if formal:
            refs += (f"production/final_chapters/chapter_{target_chapter:03d}.md",)
        decision = CreativeDecision(
            decision_id=f"decision-{uuid4().hex}", intent=intent.strip(), target_chapter=target_chapter,
            context_refs=refs, created_at=datetime.now(timezone.utc).isoformat(),
        )
        return CreativeContext(intent.strip(), target_chapter, draft, formal, recent, refs, decision)
