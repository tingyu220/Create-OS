"""父 projects 根持有创建意图，排他初始化且允许同一操作从中断恢复。"""

from pathlib import Path
from uuid import uuid4
import re

from creative_os.domains.project_authority import project_authority_lock
from creative_os.story_architecture_store import atomic_json, content_hash
from creative_os.project_write_gate import workspace_write_lease, assert_directory_available


class NovelProjectCreator:
    def __init__(self, projects_root):
        self.root = Path(projects_root).resolve()
        self.path = self.root / ".creative_os" / "new-books.json"

    def create(self, title, idea="", *, operation_id=None, author="", genre="", story_mode=True):
        from creative_os.novel_project import sanitize_project_folder_name, initialize_novel_project
        import json
        name = sanitize_project_folder_name(title)
        if not isinstance(idea, str) or len(idea) > 12000:
            raise ValueError("idea_invalid")
        operation_id = uuid4().hex if operation_id is None else operation_id
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200 or not isinstance(author, str) or not isinstance(genre, str):
            raise ValueError("project_creation_invalid")
        identity = {"title": title, "idea": idea, "author": author, "genre": genre, "story_mode": story_mode}
        fingerprint = content_hash(identity)
        with workspace_write_lease(self.root), project_authority_lock(self.root):
            assert_directory_available(self.root, name)
            data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
            record = data.get(operation_id)
            if record and record["fingerprint"] != fingerprint:
                raise ValueError("idempotency_conflict")
            path = self.root / name
            if path.resolve() != path or path.resolve().parent != self.root or path.is_symlink():
                raise ValueError("project_path_invalid")
            if record and record["status"] == "completed":
                if not path.is_dir():
                    raise ValueError("created_project_missing")
                marker = path / ".creative_os" / "creation.json"
                if not marker.is_file() or json.loads(marker.read_text(encoding="utf-8")) != {"operation_id": operation_id, "fingerprint": fingerprint}:
                    raise ValueError("project_creation_owner_conflict")
                return path
            if record is None:
                if any(child.name.casefold() == name.casefold() for child in self.root.iterdir()):
                    raise FileExistsError("project_name_conflict")
                from creative_os.project_directory import scan_project_directories
                projects, warnings = scan_project_directories(self.root)
                known_ids = set(projects) | {item["stable_id"] for item in warnings if item.get("stable_id")}
                if any(project_id.casefold() == name.casefold() for project_id in known_ids):
                    raise FileExistsError("project_identity_conflict")
                record = {"fingerprint": fingerprint, "folder": name, "status": "initializing", "identity": identity}
                data[operation_id] = record
                atomic_json(self.path, data)
            marker = path / ".creative_os" / "creation.json"
            if path.exists():
                owner = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else None
                if owner != {"operation_id": operation_id, "fingerprint": fingerprint} and not self._recoverable_marker_window(path, record):
                    raise ValueError("project_creation_owner_conflict")
            else:
                path.mkdir()
            # 先把新建目录的文件系统身份落在父根意图，再允许创建 marker 的父目录。
            # 原目录被替换或出现陌生内容时，不能凭同名意图认领它。
            if not marker.exists():
                record["directory_identity"] = self._directory_identity(path)
                atomic_json(self.path, data)
            atomic_json(marker, {"operation_id": operation_id, "fingerprint": fingerprint})
            initialize_novel_project(path, title, author=author, genre=genre, story_mode=story_mode, idea=idea)
            record["status"] = "completed"
            atomic_json(self.path, data)
            return path

    @staticmethod
    def _directory_identity(path):
        stat = path.stat()
        return {"device": stat.st_dev, "inode": stat.st_ino}

    def _recoverable_marker_window(self, path, record):
        children = list(path.iterdir())
        identity = record.get("directory_identity")
        if identity is not None and identity != self._directory_identity(path):
            return False
        if not children:
            return True
        if identity != self._directory_identity(path):
            return False
        if len(children) != 1 or children[0].name != ".creative_os" or not children[0].is_dir() or children[0].is_symlink():
            return False
        if children[0].resolve() != children[0]:
            return False
        # 原子写入可能遗留已知临时文件；保留证据，不接受其它非空目录内容。
        return all(item.is_file() and not item.is_symlink() and re.fullmatch(r"creation\.[a-f0-9]{32}\.tmp", item.name)
                   for item in children[0].iterdir())
