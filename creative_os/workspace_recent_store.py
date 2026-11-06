"""工作区 UI 最近位置；只由显式 POST 调用，不修改作品目录。"""

from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import quote, urlencode

from creative_os.domains.project_authority import project_authority_lock
from creative_os.project_registry import validated_project
from creative_os.story_architecture_store import atomic_json


def validate_location(page, chapter_number, source="auto"):
    if not isinstance(page, str) or not isinstance(source, str) or page not in {"writer", "story"} or source not in {"auto", "draft", "formal"}:
        raise ValueError("workspace_recent_location_invalid")
    if (page == "writer" and (type(chapter_number) is not int or chapter_number <= 0)) or (page == "story" and (chapter_number is not None or source != "auto")):
        raise ValueError("workspace_recent_location_invalid")


def location_url(project_id, location):
    validate_location(location["page"], location["chapter_number"], location.get("source", "auto"))
    prefix = "/p/" + quote(project_id, safe="")
    if location["page"] == "story":
        return prefix + "/story"
    return prefix + "/writer?" + urlencode({"chapter": location["chapter_number"], "source": location.get("source", "auto")})


class WorkspaceRecentStore:
    def __init__(self, projects_root):
        self.root = Path(projects_root).resolve()
        self.path = self.root / ".creative_os" / "workspace-recent.json"

    def read(self):
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or set(data) != {"schema_version", "records"} or data["schema_version"] != 1 or not isinstance(data["records"], dict):
                raise ValueError("schema")
            for key, row in data["records"].items():
                if not isinstance(row, dict) or set(row) != {"project_id", "page", "chapter_number", "source", "opened_at"} or row["project_id"] != key or not key or any(char in key for char in "/\\") or key in {".", ".."}:
                    raise ValueError("record")
                validate_location(row["page"], row["chapter_number"], row["source"])
                opened = datetime.fromisoformat(row["opened_at"])
                if opened.utcoffset() is None or opened.utcoffset().total_seconds() != 0:
                    raise ValueError("timestamp")
            return sorted(data["records"].values(), key=lambda row: (row["opened_at"], row["project_id"]), reverse=True)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise ValueError("workspace_recent_corrupt") from error

    def record(self, project_id, page, chapter_number, *, source="auto"):
        validated_project(self.root, project_id)
        validate_location(page, chapter_number, source)
        self.read()  # 损坏状态在取得写锁之前即拒绝，不以空记录掩盖它。
        with project_authority_lock(self.root):
            records = {row["project_id"]: row for row in self.read()}
            row = {"project_id": project_id, "page": page, "chapter_number": chapter_number, "source": source,
                   "opened_at": datetime.now(timezone.utc).isoformat()}
            records[project_id] = row
            atomic_json(self.path, {"schema_version": 1, "records": records})
            return row
