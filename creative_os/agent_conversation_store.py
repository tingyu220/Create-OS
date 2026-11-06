"""章节会话快照；沿用项目锁和 JSON 存储，不承担模型执行职责。"""

from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4
import hashlib

from creative_os.domains.project_authority import project_authority_lock
from creative_os.story_architecture_store import StoryArchitectureStore
from creative_os.project_write_gate import project_write_method


class AgentConversationStore:
    def __init__(self, project_root: Path, project_id: str) -> None:
        self.project_root = project_root
        self.project_id = project_id
        self.root = project_root / ".creative_os" / "agent" / "conversations"

    def read(self, chapter_number: int | None) -> dict:
        if chapter_number is not None and (type(chapter_number) is not int or chapter_number <= 0):
            raise ValueError("chapter_number_invalid")
        path = self._path(chapter_number)
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["project_id"] != self.project_id or data["chapter_number"] != chapter_number:
                raise ValueError("session_scope_mismatch")
            return data
        return {"schema_version": 1, "project_id": self.project_id,
                "chapter_number": chapter_number, "scope": "story" if chapter_number is None else "chapter",
                "session_id": StoryArchitectureStore(self.project_root, self.project_id).session_id if chapter_number is None else "session-" + hashlib.sha256(f'{self.project_id}:chapter:{chapter_number}'.encode()).hexdigest()[:32],
                "messages": [], "jobs": {}}

    def _path(self, chapter_number):
        return self.root / ("story.json" if chapter_number is None else f"chapter_{chapter_number:03d}.json")

    @project_write_method("project_root")
    def write(self, session: dict) -> None:
        # 调用方持有项目锁；同一文件同时提交消息与任务，避免半条会话。
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(session['chapter_number'])
        temporary = path.with_suffix(f".{uuid4().hex}.tmp")
        temporary.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)

    def conversation(self, chapter_number: int) -> dict:
        session = self.read(chapter_number)
        result = deepcopy(session)
        result["jobs"] = list(result["jobs"].values())
        return result

    def load_jobs(self) -> list[dict]:
        return [job for path in self.root.glob("*.json") if path.stem == "story" or path.stem.startswith("chapter_")
                for job in self.read(None if path.stem == "story" else int(path.stem.split("_")[-1]))["jobs"].values()]
