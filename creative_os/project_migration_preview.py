"""目录迁移的纯预览与短期签名校验；不执行任何写操作。"""

import hashlib
import hmac
import json
import time
import base64
from pathlib import Path
from uuid import UUID, uuid4

from creative_os.novel_project import sanitize_project_folder_name
from creative_os.project_directory import validated_project
from creative_os.project_directory_inventory import build_inventory, inventory_hash, directory_identity, safe_path


class DirectoryMigrationPreview:
    def __init__(self, projects_root, backup_root, signing_key, ttl=600):
        self.projects_root = Path(projects_root).resolve()
        self.backup_root = Path(backup_root).resolve()
        self.signing_key = signing_key if isinstance(signing_key, bytes) else str(signing_key).encode("utf-8")
        self.ttl = ttl

    def build(self, project_id):
        plan, inventory, available, reason = self.inspect(project_id)
        operation_id = str(uuid4())
        return self._result(plan, inventory, operation_id, int(time.time()) + self.ttl, available, reason)

    def inspect(self, project_id):
        """重建完整计划，不创建新的操作身份或文件。"""
        source, metadata = validated_project(self.projects_root, project_id)
        title = metadata.get("title") or metadata.get("name") or project_id
        target = sanitize_project_folder_name(title)
        safe_path(self.projects_root / target)
        root_identity, source_identity = directory_identity(self.projects_root), directory_identity(source)
        source_inventory = build_inventory(source)
        if root_identity != directory_identity(self.projects_root) or source_identity != directory_identity(source):
            raise ValueError("migration_source_changed")
        empty = not any(child.name.casefold() == target.casefold() for child in self.projects_root.iterdir())
        plan = {"project_id": project_id, "source_directory": source.name, "target_directory": target,
                "root_identity": root_identity, "source_identity": source_identity,
                "metadata_hash": next(item["sha256"] for item in source_inventory["files"] if item["path"] == "project.json"),
                "source_inventory_hash": inventory_hash(source_inventory), "target_empty": empty}
        if target == source.name:
            return plan, source_inventory, False, "already_named"
        if not empty:
            return plan, source_inventory, False, "target_directory_occupied"
        has_chinese = lambda text: any("\u4e00" <= char <= "\u9fff" for char in text)
        if has_chinese(source.name) or not has_chinese(target) or not source.name.isascii():
            return plan, source_inventory, False, "migration_not_supported"
        return plan, source_inventory, True, None

    def validate(self, token, operation_id, plan_fingerprint):
        try:
            if not isinstance(token, str) or len(token) > 4096 or str(UUID(operation_id)) != operation_id:
                raise ValueError
            body, signature = token.split(".")
            if not hmac.compare_digest(signature, hmac.new(self.signing_key, body.encode("ascii"), hashlib.sha256).hexdigest()):
                raise ValueError
            data = json.loads(base64.urlsafe_b64decode(body.encode("ascii")))
            if set(data) != {"operation_id", "plan_fingerprint", "project_id", "expires_at"} or data["operation_id"] != operation_id or data["plan_fingerprint"] != plan_fingerprint or type(data["expires_at"]) is not int or data["expires_at"] <= int(time.time()):
                raise ValueError
        except (ValueError, TypeError, AttributeError, UnicodeError) as exc:
            raise ValueError("preview_token_invalid") from exc
        plan, inventory, available, reason = self.inspect(data["project_id"])
        if inventory_hash(plan) != plan_fingerprint or not available:
            raise ValueError("preview_stale")
        return self._result(plan, inventory, operation_id, data["expires_at"], available, reason)

    def _result(self, plan, inventory, operation_id, expires_at, available, reason):
        fingerprint = inventory_hash(plan)
        body = base64.urlsafe_b64encode(json.dumps({"operation_id": operation_id, "plan_fingerprint": fingerprint,
                    "project_id": plan["project_id"], "expires_at": expires_at}, sort_keys=True).encode()).decode("ascii")
        token = body + "." + hmac.new(self.signing_key, body.encode("ascii"), hashlib.sha256).hexdigest()
        backup = self.backup_root / operation_id / "project"
        return {"available": available, "reason_code": reason, "project_id": plan["project_id"],
                "source_directory": plan["source_directory"], "target_directory": plan["target_directory"],
                "operation_id": operation_id, "plan_fingerprint": fingerprint, "preview_token": token,
                "expires_at": expires_at, "reload_required": True, "source_inventory_hash": plan["source_inventory_hash"],
                "backup_directory": backup.relative_to(self.projects_root.parent).as_posix(),
                "file_count": len(inventory["files"]), "directory_count": len(inventory["directories"]),
                "impact": "完整备份后仅整理目录名，稿件与稳定作品ID保持不变。"}
