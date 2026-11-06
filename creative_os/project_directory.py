"""稳定项目 ID 到安全直接子目录的纯查询映射；不创建缓存或 Runtime。"""

import json
from pathlib import Path


def validate_project_id(project_id):
    if (not isinstance(project_id, str) or not project_id or project_id != project_id.strip()
            or len(project_id) > 200 or project_id in {".", ".."}
            or any(char in project_id for char in "/\\") or any(ord(char) < 32 for char in project_id)):
        raise ValueError("project_scope_mismatch")


def read_project_metadata(projects_root, directory):
    """目录和元数据均不得经链接跳出根；身份只取 project.json.id。"""
    parent, root = Path(projects_root).resolve(), Path(directory).absolute()
    metadata_path = root / "project.json"
    if root.is_symlink() or root.resolve() != root or root.parent != parent or not root.is_dir() or not metadata_path.is_file():
        raise ValueError("project_not_found")
    if metadata_path.is_symlink() or metadata_path.resolve() != metadata_path or metadata_path.stat().st_size > 65536:
        raise ValueError("project_metadata_invalid")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise ValueError("project_metadata_invalid")
    validate_project_id(metadata.get("id"))
    return metadata


def scan_project_directories(projects_root):
    parent = Path(projects_root).resolve()
    if not parent.is_dir():
        raise OSError("projects_root_unavailable")
    candidates, warnings, directory_names = [], [], {}
    for child in sorted(parent.iterdir(), key=lambda path: path.name.casefold()):
        if child.name in {".creative_os", ".backup", ".git", ".superpowers"}:
            continue
        try:
            if not child.is_dir():
                continue
            if child.name.startswith(".") and not (child / "project.json").exists():
                continue
            directory_names[child.name.casefold()] = child
            metadata = read_project_metadata(parent, child)
            candidates.append((metadata["id"], child, metadata))
        except (OSError, ValueError, TypeError):
            warnings.append({"project_id": child.name, "directory": child.name, "code": "project_unavailable",
                             "message": "作品目录或元数据暂不可用。"})
    by_id = {}
    for project_id, root, metadata in candidates:
        by_id.setdefault(project_id.casefold(), []).append((project_id, root, metadata))
    blocked = {key for key, rows in by_id.items() if len(rows) != 1}
    # 不把目录别名当成身份；别名占用另一身份时，两方都拒绝，避免旧链接静默串书。
    for project_id, root, _ in candidates:
        occupied = directory_names.get(project_id.casefold())
        if occupied is not None and occupied != root:
            blocked.add(project_id.casefold())
            blocked.update(other_id.casefold() for other_id, other_root, _ in candidates if other_root == occupied)
    result = {}
    for project_id, root, metadata in candidates:
        if project_id.casefold() in blocked:
            warnings.append({"project_id": project_id, "stable_id": project_id, "directory": root.name,
                             "code": "project_identity_ambiguous", "message": "作品 ID 重复或与其他目录冲突，已拒绝打开以免串书。"})
        else:
            result[project_id] = (root, metadata)
    return result, warnings


def validated_project(projects_root, project_id):
    validate_project_id(project_id)
    projects, warnings = scan_project_directories(projects_root)
    if project_id in projects:
        return projects[project_id]
    if any(item.get("stable_id") == project_id for item in warnings):
        raise ValueError("project_identity_ambiguous")
    raise ValueError("project_not_found")
