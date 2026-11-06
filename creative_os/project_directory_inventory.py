"""项目目录的只读清单与稳定摘要。"""

import hashlib
import json
import os
import shutil
from pathlib import Path


def _reject_links(path: Path) -> None:
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise ValueError("project_link_unsafe")
    if path.exists():
        info = path.lstat()
        if getattr(info, "st_file_attributes", 0) & 0x400 or (path.is_file() and info.st_nlink != 1):
            raise ValueError("project_link_unsafe")


def safe_path(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        _reject_links(item)
    return path


def directory_identity(root):
    root = safe_path(root)
    info = root.stat()
    if not root.is_dir():
        raise ValueError("project_directory_invalid")
    return {"device": info.st_dev, "inode": info.st_ino}


def build_inventory(root):
    original = safe_path(root)
    root = original.resolve()
    if not root.is_dir():
        raise ValueError("project_not_found")
    _reject_links(root)
    files, directories = [], []
    for path in sorted(root.rglob("*"), key=lambda item: (item.relative_to(root).as_posix().casefold(), item.relative_to(root).as_posix())):
        _reject_links(path)
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            directories.append(relative)
        elif path.is_file():
            data = path.read_bytes()
            files.append({"path": relative, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        else:
            raise ValueError("project_entry_unsafe")
    return {"directories": directories, "files": files}


def copy_verified(source, backup, manifest):
    """只创建全新副本；部分副本保留，调用方不得把失败当作已验证。"""
    source, backup = safe_path(source), safe_path(backup)
    if build_inventory(source) != manifest:
        raise ValueError("migration_source_changed")
    backup.mkdir(exist_ok=False)
    for relative in manifest["directories"]:
        (backup / relative).mkdir(parents=True, exist_ok=False)
    for item in manifest["files"]:
        relative = item["path"]
        src, dst = safe_path(source / relative), safe_path(backup / relative)
        with src.open("rb") as reader, dst.open("xb") as writer:
            shutil.copyfileobj(reader, writer)
            writer.flush()
            os.fsync(writer.fileno())
        shutil.copystat(src, dst, follow_symlinks=False)
    if build_inventory(source) != manifest or build_inventory(backup) != manifest:
        raise ValueError("migration_backup_mismatch")


def rename_no_replace(source, target):
    """Windows原生同卷rename拒绝已有目标；其他平台明确拒绝，不降级覆盖。"""
    source, target = safe_path(source), safe_path(target)
    if os.name != "nt":
        raise ValueError("migration_atomic_rename_unsupported")
    if source.parent != target.parent or source.stat().st_dev != target.parent.stat().st_dev:
        raise ValueError("migration_same_root_required")
    # Windows的os.rename使用不含REPLACE_EXISTING/COPY_ALLOWED的MoveFileExW。
    # 目标存在检查由系统原子完成，不能用exists检查替代。
    os.rename(source, target)


def inventory_hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
